from __future__ import annotations

import logging
import shutil
import time
import zipfile
from pathlib import Path
from typing import Callable

from ..analysis.layout_analyzer import AnalyzerConfig, LayoutAnalyzer
from ..config import Settings
from ..domain.layout import LayoutDocument
from ..infrastructure.pdf.assets import AssetWriter
from ..infrastructure.pdf.input import InputNormalizer
from ..infrastructure.pdf.ocr import OcrEngine
from ..infrastructure.pdf.rasterizer import page_similarity, render_previews
from ..infrastructure.pdf.reader import PdfReader, ReaderConfig
from ..infrastructure.toolchain.base import Toolchain
from ..renderers.base import DocumentRenderer, OutputFormat, RenderContext
from ..renderers.docx.renderer import DocxRenderer
from ..renderers.latex.exact import LatexExactRenderer
from ..renderers.latex.flow import LatexFlowRenderer
from .dto import Artifact, ConversionOptions, ConversionReport, LatexMode, PageReport, Preview

log = logging.getLogger(__name__)
Progress = Callable[[int, str], None]


class ConversionPipeline:
    def __init__(self, settings: Settings, toolchain: Toolchain, ocr: OcrEngine | None = None):
        self.settings = settings
        self.toolchain = toolchain
        self.ocr = ocr or OcrEngine()
        self.normalizer = InputNormalizer(settings.max_upload_mb * 1024 * 1024)

    def latex_renderer(self, mode: LatexMode) -> DocumentRenderer:
        return LatexExactRenderer() if mode is LatexMode.EXACT else LatexFlowRenderer()

    def run(self, job_dir: Path, data: bytes, filename: str, options: ConversionOptions,
            progress: Progress = lambda p, m: None) -> tuple[list[Artifact], ConversionReport]:
        t0 = time.perf_counter()
        timings: dict[str, float] = {}
        report = ConversionReport()
        artifacts: list[Artifact] = []

        def mark(name: str, start: float) -> float:
            now = time.perf_counter()
            timings[name] = round(now - start, 3)
            return now

        progress(3, "Chuẩn hoá đầu vào")
        norm = self.normalizer.normalize(data, filename)
        stem = norm.stem
        input_dir = job_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        src_pdf = input_dir / f"{stem}.pdf"
        src_pdf.write_bytes(norm.pdf_bytes)
        report.source_kind = norm.source_kind
        artifacts.append(self._artifact(job_dir, src_pdf, "input", "PDF đầu vào"))
        t = mark("normalize", t0)

        progress(8, "Đọc PDF: chữ, font, ảnh, vector, bảng")
        work = job_dir / "work"
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        assets = AssetWriter(work / "assets")
        max_pages = min(options.max_pages or self.settings.max_pages, self.settings.max_pages)
        cfg = ReaderConfig(password=options.password, max_pages=max_pages, ocr=options.ocr,
                           ocr_language=options.ocr_language, detect_tables=options.detect_tables,
                           vector_dpi=self.settings.vector_dpi)
        document = PdfReader(assets, self.ocr).read(norm.pdf_bytes, filename, cfg)
        report.total_pages = document.total_pages
        report.processed_pages = document.page_count
        report.warnings.extend(document.warnings)
        t = mark("read", t)

        progress(35, "Phân tích bố cục (dòng, tab, đoạn, cột, bảng)")
        layout = LayoutAnalyzer(AnalyzerConfig(detect_columns=options.detect_columns,
                                               use_tables=options.detect_tables)).analyze(document)
        report.pages = self._page_reports(layout)
        t = mark("analyze", t)

        out_root = job_dir / "output"
        if out_root.exists():
            shutil.rmtree(out_root, ignore_errors=True)
        latex_pdf: Path | None = None
        docx_pdf: Path | None = None

        if OutputFormat.LATEX in options.formats:
            progress(45, f"Sinh LaTeX ({options.latex_mode.value})")
            ldir = out_root / "latex"
            res = self.latex_renderer(options.latex_mode).render(
                layout, RenderContext(ldir, assets.root, stem))
            report.warnings.extend(res.warnings)
            artifacts.append(self._artifact(job_dir, res.main_file, "latex", "Mã nguồn LaTeX (.tex)"))
            t = mark("latex_render", t)
            if options.compile_latex:
                progress(55, "Biên dịch LaTeX bằng XeLaTeX")
                cr = self.toolchain.compile_latex(ldir, res.main_file.name, self.settings.toolchain_timeout)
                report.latex_log = cr.log
                if cr.success and cr.pdf_path:
                    latex_pdf = cr.pdf_path
                    artifacts.append(self._artifact(job_dir, cr.pdf_path, "latex_pdf", "PDF biên dịch từ LaTeX"))
                else:
                    report.warnings.append("Biên dịch LaTeX không thành công – xem log.")
                t = mark("latex_compile", t)

        if OutputFormat.DOCX in options.formats:
            progress(70, "Sinh DOCX")
            ddir = out_root / "docx"
            res = DocxRenderer().render(layout, RenderContext(ddir, assets.root, stem))
            artifacts.append(self._artifact(job_dir, res.main_file, "docx", "Tài liệu Word (.docx)"))
            t = mark("docx_render", t)
            if options.preview_docx:
                progress(78, "Chuyển DOCX sang PDF để so sánh")
                dr = self.toolchain.docx_to_pdf(res.main_file, job_dir / "work" / "docx_pdf",
                                                self.settings.toolchain_timeout)
                report.docx_log = dr.log
                if dr.success and dr.pdf_path:
                    docx_pdf = dr.pdf_path
                    artifacts.append(self._artifact(job_dir, dr.pdf_path, "docx_pdf", "PDF xem trước của DOCX"))
                t = mark("docx_preview", t)

        progress(88, "Tạo ảnh xem trước và đo độ giống")
        report.previews = self._previews(job_dir, src_pdf, latex_pdf, docx_pdf, document.page_count)
        if latex_pdf:
            report.fidelity["latex"] = self._safe_similarity(src_pdf, latex_pdf)
        if docx_pdf:
            report.fidelity["docx"] = self._safe_similarity(src_pdf, docx_pdf)
        t = mark("preview", t)

        progress(96, "Đóng gói kết quả")
        if out_root.exists():
            zpath = job_dir / f"{stem}-pdfconv.zip"
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
                for p in sorted(out_root.rglob("*")):
                    if p.is_file() and p.suffix not in (".aux", ".out"):
                        z.write(p, p.relative_to(out_root).as_posix())
            artifacts.insert(0, self._artifact(job_dir, zpath, "zip", "Tải tất cả (.zip)"))
        mark("package", t)
        timings["total"] = round(time.perf_counter() - t0, 3)
        report.timings = timings
        return artifacts, report

    @staticmethod
    def _artifact(job_dir: Path, path: Path, kind: str, label: str) -> Artifact:
        return Artifact(kind=kind, path=path.relative_to(job_dir).as_posix(), label=label,
                        size=path.stat().st_size if path.exists() else 0)

    @staticmethod
    def _page_reports(layout: LayoutDocument) -> list[PageReport]:
        out = []
        for lp in layout.pages:
            p = lp.page
            out.append(PageReport(
                index=p.index, width=round(p.width, 1), height=round(p.height, 1),
                text_lines=len(p.lines), images=len(p.images), shapes=p.shape_count,
                tables=len(p.tables), columns=max((b.columns for b in lp.bands), default=1),
                scanned=p.is_scanned, ocr=p.ocr_applied, complex_graphics=p.complex_graphics,
                warnings=list(p.warnings)))
        return out

    def _previews(self, job_dir: Path, src: Path, latex_pdf: Path | None, docx_pdf: Path | None,
                  n: int) -> list[Preview]:
        pv = job_dir / "previews"
        if pv.exists():
            shutil.rmtree(pv, ignore_errors=True)
        dpi = self.settings.preview_dpi
        cols: dict[str, list[Path]] = {}
        for key, pdf in (("original", src), ("latex", latex_pdf), ("docx", docx_pdf)):
            if pdf is None:
                continue
            try:
                cols[key] = render_previews(pdf, pv, key, dpi=dpi, max_pages=min(n, 60))
            except Exception as exc:
                log.warning("Không tạo được ảnh xem trước %s: %s", key, exc)
        previews = []
        for i in range(min(n, 60)):
            item = Preview(page=i + 1)
            for key, paths in cols.items():
                if i < len(paths):
                    setattr(item, key, paths[i].relative_to(job_dir).as_posix())
            previews.append(item)
        return previews

    @staticmethod
    def _safe_similarity(a: Path, b: Path) -> list[float]:
        try:
            return page_similarity(a, b)
        except Exception as exc:
            log.warning("Không đo được độ giống: %s", exc)
            return []
