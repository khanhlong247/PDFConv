from __future__ import annotations

import logging
from pathlib import Path

import pymupdf

from ...domain.geometry import Rect
from ...domain.models import ImageElement, ImageRole
from .assets import AssetWriter

log = logging.getLogger(__name__)


def _unpremultiplied_png(pix: pymupdf.Pixmap) -> bytes:
    import io

    from PIL import Image

    img = Image.frombytes("RGBa", (pix.width, pix.height), pix.samples).convert("RGBA")
    alpha = img.getchannel("A")
    white = Image.new("RGB", img.size, (255, 255, 255))
    rgb = Image.composite(img.convert("RGB"), white, alpha.point(lambda a: 255 if a else 0))
    rgb.putalpha(alpha)
    buf = io.BytesIO()
    rgb.save(buf, "PNG")
    return buf.getvalue()


class PageRasterizer:
    def __init__(self, assets: AssetWriter):
        self.assets = assets

    def vector_layer(self, doc: pymupdf.Document, page_index: int, exclude: list[Rect],
                     dpi: int, tag: str) -> ImageElement | None:

        tmp = pymupdf.open()
        try:
            tmp.insert_pdf(doc, from_page=page_index, to_page=page_index, annots=False)
            pg = tmp[0]
            pg.add_redact_annot(pg.rect, fill=False)
            pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                                graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            if exclude:
                for r in exclude:
                    pg.add_redact_annot(pymupdf.Rect(*r.expand(1.5).as_tuple()), fill=False)
                pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                    graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                    text=pymupdf.PDF_REDACT_TEXT_NONE)
            probe = pg.get_pixmap(dpi=72, alpha=False)
            if probe.is_unicolor and probe.pixel(0, 0)[:3] == (255, 255, 255):
                return None
            pix = pg.get_pixmap(dpi=dpi, alpha=True)
            rel, digest = self.assets.save(_unpremultiplied_png(pix), "png", prefix=f"layer_{tag}")
            return ImageElement(bbox=Rect.of(pg.rect), file=rel, pixel_width=pix.width,
                                pixel_height=pix.height, has_alpha=True, z=-1,
                                role=ImageRole.VECTOR_LAYER, digest=digest)
        except Exception as exc:
            log.warning("Không tạo được lớp vector trang %s: %s", page_index + 1, exc)
            return None
        finally:
            tmp.close()


def render_previews(pdf_path: Path, out_dir: Path, prefix: str, dpi: int = 72,
                    max_pages: int = 60) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            p = out_dir / f"{prefix}_{i + 1:03d}.png"
            page.get_pixmap(dpi=dpi, alpha=False).save(p)
            paths.append(p)
    return paths


def page_similarity(a_pdf: Path, b_pdf: Path, max_pages: int = 60) -> list[float]:
    from PIL import Image, ImageChops, ImageFilter, ImageStat

    scores: list[float] = []
    with pymupdf.open(a_pdf) as da, pymupdf.open(b_pdf) as db:
        for i in range(min(len(da), len(db), max_pages)):
            pa = da[i].get_pixmap(dpi=36, colorspace=pymupdf.csGRAY, alpha=False)
            pb = db[i].get_pixmap(dpi=36, colorspace=pymupdf.csGRAY, alpha=False)
            blur = ImageFilter.GaussianBlur(1.2)
            ia = Image.frombytes("L", (pa.width, pa.height), pa.samples).filter(blur)
            ib = Image.frombytes("L", (pb.width, pb.height), pb.samples).resize(ia.size).filter(blur)
            diff = ImageStat.Stat(ImageChops.difference(ia, ib)).mean[0]
            ink = max(1.0, 255 - min(ImageStat.Stat(ia).mean[0], ImageStat.Stat(ib).mean[0]))
            scores.append(round(max(0.0, 1.0 - diff / ink), 4))
    return scores
