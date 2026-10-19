from __future__ import annotations

import contextlib
import io
import logging
from dataclasses import dataclass

import pymupdf

from ...domain.errors import PasswordRequiredError, UnsupportedInputError
from ...domain.geometry import Point, Rect
from ...domain.models import (Color, Document, Glyph, ImageRole, Page, TableCell, TableElement,
                              TextLine, TextSpan, angle_from_dir)
from ...domain.text import clean_char
from .assets import AssetWriter
from .fonts import FontNormalizer
from .graphics import ShapeExtractor, page_drawings
from .images import ImageExtractor
from .ocr import OcrEngine
from .rasterizer import PageRasterizer

log = logging.getLogger(__name__)

TEXT_FLAGS = (pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP)


@dataclass(slots=True)
class ReaderConfig:
    password: str | None = None
    max_pages: int | None = None
    ocr: bool = False
    ocr_language: str = "vie+eng"
    ocr_dpi: int = 300
    detect_tables: bool = True
    vector_dpi: int = 150
    max_vector_shapes: int = 2500
    build_vector_layers: bool = True


class PdfReader:
    def __init__(self, assets: AssetWriter, ocr: OcrEngine | None = None):
        self.assets = assets
        self.fonts = FontNormalizer()
        self.images = ImageExtractor(assets)
        self.shapes = ShapeExtractor()
        self.rasterizer = PageRasterizer(assets)
        self.ocr = ocr

    def open(self, pdf_bytes: bytes, cfg: ReaderConfig) -> pymupdf.Document:
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise UnsupportedInputError(f"PDF hỏng hoặc không đọc được: {exc}") from exc
        if doc.needs_pass and not doc.authenticate(cfg.password or ""):
            doc.close()
            raise PasswordRequiredError(
                "PDF được bảo vệ bằng mật khẩu." if not cfg.password else "Mật khẩu PDF không đúng.")
        if doc.page_count == 0:
            doc.close()
            raise UnsupportedInputError("PDF không có trang nào.")

        try:
            if any(p.first_annot or p.first_widget for p in doc):
                doc.bake(annots=True, widgets=True)
        except Exception as exc:
            log.info("Không bake được annotation: %s", exc)
        return doc

    def read(self, pdf_bytes: bytes, name: str, cfg: ReaderConfig) -> Document:
        doc = self.open(pdf_bytes, cfg)
        try:
            meta = {k: v for k, v in (doc.metadata or {}).items() if v}
            total = doc.page_count
            n = min(total, cfg.max_pages) if cfg.max_pages else total
            pages: list[Page] = []
            for i in range(n):
                pages.append(self._read_page(doc, i, cfg))
            warnings = []
            if n < total:
                warnings.append(f"Chỉ xử lý {n}/{total} trang đầu (giới hạn số trang).")
            try:
                for w in (pymupdf.TOOLS.mupdf_warnings() or "").splitlines()[:20]:
                    if w.strip():
                        warnings.append(f"MuPDF: {w.strip()}")
                pymupdf.TOOLS.reset_mupdf_warnings()
            except Exception:
                pass
            return Document(name=name, pages=pages, metadata=meta, warnings=warnings, total_pages=total)
        finally:
            doc.close()

    def _read_page(self, doc: pymupdf.Document, index: int, cfg: ReaderConfig) -> Page:
        page = doc[index]
        warnings: list[str] = []
        if page.rotation:
            try:
                page.remove_rotation()
            except Exception as exc:
                warnings.append(f"Không chuẩn hoá được hướng xoay trang: {exc}")
        rect = page.rect
        out = Page(index=index, width=float(rect.width), height=float(rect.height))
        out.warnings = warnings

        try:
            bboxlog = page.get_bboxlog()
        except Exception:
            bboxlog = []
        invisible = [Rect.of(r) for t, r in bboxlog if t == "ignore-text"]
        has_shading = any(t == "fill-shade" for t, _ in bboxlog)

        out.images, img_warn = self.images.extract(doc, page, bboxlog)
        warnings.extend(img_warn)

        lines, hidden_lines = self._extract_text(page, invisible)
        out.lines = lines
        n_chars = sum(len(s.text.strip()) for ln in lines for s in ln.spans)
        bad = sum(s.text.count("�") for ln in lines for s in ln.spans)
        if n_chars and bad / n_chars > 0.3:
            out.text_reliable = False
            warnings.append("Font không có bảng mã Unicode: chữ trích xuất có thể sai.")

        page_area = out.width * out.height
        img_cover = sum(im.bbox.overlap_area(out.rect) for im in out.images) / max(page_area, 1)
        out.is_scanned = n_chars == 0 and img_cover >= 0.5

        if cfg.ocr and (out.is_scanned or not out.text_reliable):
            if hidden_lines and out.is_scanned:
                out.lines = hidden_lines
                out.ocr_applied = True
            elif self.ocr and self.ocr.available:
                try:
                    tp = self.ocr.textpage(page, cfg.ocr_language, cfg.ocr_dpi)
                    out.lines, _ = self._extract_text(page, [], textpage=tp)
                    out.ocr_applied = True
                    out.text_reliable = True
                except Exception as exc:
                    warnings.append(f"OCR thất bại: {exc}")
            else:
                warnings.append("Trang scan nhưng máy chủ chưa cài Tesseract OCR; giữ dạng ảnh.")
            if out.ocr_applied:
                out.images = [im for im in out.images
                              if im.bbox.overlap_area(out.rect) < 0.5 * page_area]
        text_log = [(i, Rect.of(r)) for i, (t, r) in enumerate(bboxlog) if t.endswith("-text")]
        for im in out.images:
            cover = im.bbox.overlap_area(out.rect) / max(page_area, 1)
            if out.is_scanned and not out.ocr_applied and cover >= 0.5:
                im.role = ImageRole.PAGE_SCAN
            elif any(i > im.z and im.bbox.contains_point(r.cx, r.cy) and not r.is_empty
                     for i, r in text_log):
                im.role = ImageRole.BACKGROUND

        drawings = page_drawings(page)
        out.shape_count = len(drawings)
        out.complex_graphics = has_shading or len(drawings) > cfg.max_vector_shapes
        if not out.complex_graphics:
            out.shapes = self.shapes.extract(drawings)

        if cfg.detect_tables and drawings:
            out.tables = self._find_tables(page, warnings)

        if cfg.build_vector_layers and (drawings or has_shading):
            excl = [t.bbox for t in out.tables]
            out.vector_layer = self.rasterizer.vector_layer(doc, index, excl, cfg.vector_dpi,
                                                            tag=f"p{index + 1:03d}")
            if out.complex_graphics:
                out.vector_layer_full = (self.rasterizer.vector_layer(doc, index, [], cfg.vector_dpi,
                                                                      tag=f"p{index + 1:03d}full")
                                         if excl else out.vector_layer)
        if out.complex_graphics:
            warnings.append(f"Trang có đồ hoạ phức tạp ({len(drawings)} đối tượng"
                            f"{', gradient' if has_shading else ''}): lớp vector được raster hoá.")
        return out

    def _extract_text(self, page: pymupdf.Page, invisible: list[Rect],
                      textpage=None) -> tuple[list[TextLine], list[TextLine]]:
        try:
            raw = page.get_text("rawdict", flags=TEXT_FLAGS, textpage=textpage)
        except Exception as exc:
            log.warning("Lỗi trích xuất chữ trang %s: %s", page.number + 1, exc)
            return [], []
        visible: list[TextLine] = []
        hidden: list[TextLine] = []
        for block in raw.get("blocks", ()):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", ()):
                vis_spans, hid_spans = [], []
                for sp in line.get("spans", ()):
                    span = self._make_span(sp)
                    if span is None:
                        continue
                    if span.alpha == 0 or self._is_invisible(span.bbox, invisible):
                        hid_spans.append(span)
                    else:
                        vis_spans.append(span)
                dx, dy = line.get("dir", (1.0, 0.0))
                angle = angle_from_dir(dx, dy)
                vertical = bool(line.get("wmode", 0))
                for spans, bucket in ((vis_spans, visible), (hid_spans, hidden)):
                    if spans:
                        bbox = Rect.union_all(s.bbox for s in spans)
                        bucket.append(TextLine(spans=spans, bbox=bbox, angle=angle, vertical=vertical))
        return visible, hidden

    def _make_span(self, sp: dict) -> TextSpan | None:
        glyphs: list[Glyph] = []
        for ch in sp.get("chars", ()):
            c = clean_char(ch.get("c", ""))
            if not c:
                continue
            x0, _, x1, _ = ch["bbox"]
            ox = ch.get("origin", (x0, 0))[0]
            if len(c) == 1:
                glyphs.append(Glyph(c, float(min(x0, ox)), float(x1)))
            else:
                w = (x1 - x0) / len(c)
                glyphs.extend(Glyph(cc, x0 + k * w, x0 + (k + 1) * w) for k, cc in enumerate(c))
        text = "".join(g.char for g in glyphs)
        if not text.strip():
            return None
        size = float(sp.get("size") or 0)
        if size <= 0.5:
            return None
        flags = int(sp.get("flags", 0))
        font = self.fonts.normalize(sp.get("font", ""), flags)
        ox, oy = sp.get("origin", (glyphs[0].x0, sp["bbox"][3]))
        return TextSpan(
            text=text,
            bbox=Rect.of(sp["bbox"]),
            origin=Point(float(ox), float(oy)),
            font=font,
            size=size,
            color=Color.from_int(int(sp.get("color", 0)) & 0xFFFFFF),
            glyphs=glyphs,
            superscript=bool(flags & 1),
            alpha=float(sp.get("alpha", 255)) / 255.0,
        )

    @staticmethod
    def _is_invisible(bbox: Rect, invisible: list[Rect]) -> bool:
        if not invisible or bbox.area <= 0:
            return False
        cx, cy = bbox.cx, bbox.cy
        return any(r.expand(0.5).contains_point(cx, cy) for r in invisible)

    @staticmethod
    def _find_tables(page: pymupdf.Page, warnings: list[str]) -> list[TableElement]:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                found = page.find_tables()
        except Exception as exc:
            warnings.append(f"Bỏ qua nhận diện bảng: {exc}")
            return []
        out: list[TableElement] = []
        for t in found.tables:
            cells = [Rect.of(c) for c in t.cells if c]
            if len(cells) < 2:
                continue
            cols = _cluster([c.x0 for c in cells] + [c.x1 for c in cells])
            rows = _cluster([c.y0 for c in cells] + [c.y1 for c in cells])
            if len(cols) < 3 or len(rows) < 3:
                continue
            tcells = []
            for c in cells:
                ci0, ci1 = _nearest(cols, c.x0), _nearest(cols, c.x1)
                ri0, ri1 = _nearest(rows, c.y0), _nearest(rows, c.y1)
                if ci1 <= ci0 or ri1 <= ri0:
                    continue
                tcells.append(TableCell(row=ri0, col=ci0, row_span=ri1 - ri0, col_span=ci1 - ci0, bbox=c))
            if tcells:
                out.append(TableElement(bbox=Rect(cols[0], rows[0], cols[-1], rows[-1]),
                                        col_edges=cols, row_edges=rows, cells=tcells))
        return out


def _cluster(values: list[float], tol: float = 1.5) -> list[float]:
    vals = sorted(values)
    groups: list[list[float]] = []
    for v in vals:
        if groups and v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _nearest(edges: list[float], v: float) -> int:
    return min(range(len(edges)), key=lambda i: abs(edges[i] - v))
