from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass

import pymupdf
from PIL import Image, ImageOps

from ...domain.geometry import Rect
from ...domain.models import ImageElement, ImageRole
from .assets import AssetWriter

log = logging.getLogger(__name__)

_EPS = 1e-3
MAX_PIXELS = 40_000_000


@dataclass(slots=True)
class _Decoded:
    image: Image.Image
    jpeg_bytes: bytes | None


def _pix_to_pil(pix: pymupdf.Pixmap) -> Image.Image:
    mode = {1: "L", 3: "RGB"}.get(pix.n - pix.alpha)
    if mode is None:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        mode = "RGB"
    if pix.alpha:
        base_mode = mode + "A" if mode == "RGB" else "LA"
        return Image.frombytes(base_mode, (pix.width, pix.height), pix.samples)
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)


class ImageExtractor:
    def __init__(self, assets: AssetWriter):
        self.assets = assets
        self._decoded: dict[int, _Decoded | None] = {}
        self._saved: dict[tuple, tuple[str, str, int, int, bool]] = {}

    def _decode_xref(self, doc: pymupdf.Document, xref: int) -> _Decoded | None:
        if xref in self._decoded:
            return self._decoded[xref]
        result: _Decoded | None = None
        try:
            result = self._decode_xref_impl(doc, xref)
        except Exception as exc:
            log.warning("Không giải mã được ảnh xref %s: %s", xref, exc)
        self._decoded[xref] = result
        return result

    def _decode_xref_impl(self, doc: pymupdf.Document, xref: int) -> _Decoded:
        is_stencil = doc.xref_get_key(xref, "ImageMask")[1] == "true"
        smask_type, smask_val = doc.xref_get_key(xref, "SMask")
        mask_type, mask_val = doc.xref_get_key(xref, "Mask")

        pix = pymupdf.Pixmap(doc, xref)
        if pix.width * pix.height > MAX_PIXELS:
            f = math.sqrt(MAX_PIXELS / (pix.width * pix.height))
            pix = pymupdf.Pixmap(pix, max(1, int(pix.width * f)), max(1, int(pix.height * f)), None)
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
        if pix.colorspace is None or pix.n not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

        if is_stencil:
            gray = _pix_to_pil(pix).convert("L")
            rgba = Image.new("RGBA", gray.size, (0, 0, 0, 0))
            rgba.putalpha(ImageOps.invert(gray))
            return _Decoded(rgba, None)

        image = _pix_to_pil(pix)
        alpha: Image.Image | None = None
        if smask_type == "xref":
            alpha = self._load_mask(doc, int(smask_val.split()[0]), image.size, invert=False)
        elif mask_type == "xref":
            alpha = self._load_mask(doc, int(mask_val.split()[0]), image.size, invert=True)
        if alpha is not None:
            image = image.convert("RGBA") if image.mode != "L" else image.convert("LA")
            image.putalpha(alpha)
            if image.mode == "LA":
                image = image.convert("RGBA")
            return _Decoded(image, None)

        jpeg = None
        try:
            info = doc.extract_image(xref)
            if (info.get("ext") in ("jpeg", "jpg") and info.get("cs-name") in ("DeviceRGB", "DeviceGray")
                    and not info.get("smask") and info.get("width") == image.width
                    and doc.xref_get_key(xref, "Decode")[0] == "null"):
                jpeg = info["image"]
        except Exception:  # noqa: BLE001
            jpeg = None
        return _Decoded(image, jpeg)

    @staticmethod
    def _load_mask(doc: pymupdf.Document, xref: int, size: tuple[int, int], invert: bool) -> Image.Image | None:
        try:
            m = pymupdf.Pixmap(doc, xref)
            if m.alpha:
                m = pymupdf.Pixmap(m, 0)
            if m.n != 1:
                m = pymupdf.Pixmap(pymupdf.csGRAY, m)
            mask = Image.frombytes("L", (m.width, m.height), m.samples)
            if mask.size != size:
                mask = mask.resize(size, Image.BILINEAR)
            return ImageOps.invert(mask) if invert else mask
        except Exception as exc:  # noqa: BLE001
            log.warning("Không đọc được mask xref %s: %s", xref, exc)
            return None

    @staticmethod
    def _apply_transform(img: Image.Image, matrix: tuple[float, ...], bbox: Rect) -> Image.Image:
        a, b, c, d, e, f = matrix
        if abs(b) < _EPS and abs(c) < _EPS and a > 0 and d > 0:
            return img
        if abs(b) < _EPS and abs(c) < _EPS:
            if a < 0:
                img = ImageOps.mirror(img)
            if d < 0:
                img = ImageOps.flip(img)
            return img
        det = a * d - b * c
        if abs(det) < 1e-9 or bbox.is_empty:
            return img
        w_px, h_px = img.size
        scale = max(w_px / max(math.hypot(a, b), 1e-6), h_px / max(math.hypot(c, d), 1e-6))
        scale = min(scale, 4000 / max(bbox.width, bbox.height, 1))
        out_w = max(1, round(bbox.width * scale))
        out_h = max(1, round(bbox.height * scale))
        i00, i01, i10, i11 = d / det, -c / det, -b / det, a / det
        ox, oy = bbox.x0 - e, bbox.y0 - f
        coeffs = (w_px * i00 / scale, w_px * i01 / scale, w_px * (i00 * ox + i01 * oy),
                  h_px * i10 / scale, h_px * i11 / scale, h_px * (i10 * ox + i11 * oy))
        src = img.convert("RGBA")
        return src.transform((out_w, out_h), Image.AFFINE, coeffs, resample=Image.BICUBIC,
                             fillcolor=(0, 0, 0, 0))

    def _store(self, key: tuple, dec: _Decoded, matrix, bbox: Rect) -> tuple[str, str, int, int, bool]:
        if key in self._saved:
            return self._saved[key]
        img = self._apply_transform(dec.image, matrix, bbox)
        has_alpha = img.mode in ("RGBA", "LA")
        if has_alpha and img.getextrema()[-1][0] == 255:
            img = img.convert("RGB")
            has_alpha = False
        if img is dec.image and dec.jpeg_bytes is not None:
            rel, digest = self.assets.save(dec.jpeg_bytes, "jpg")
        else:
            buf = io.BytesIO()
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA" if has_alpha else "RGB")
            img.save(buf, "PNG", optimize=False)
            rel, digest = self.assets.save(buf.getvalue(), "png")
        res = (rel, digest, img.width, img.height, has_alpha)
        self._saved[key] = res
        return res

    def extract(self, doc: pymupdf.Document, page: pymupdf.Page,
                bboxlog: list[tuple[str, tuple]]) -> tuple[list[ImageElement], list[str]]:
        warnings: list[str] = []
        page_rect = Rect.of(page.rect)
        image_log = [(i, Rect.of(r)) for i, (t, r) in enumerate(bboxlog) if "image" in t]
        used: set[int] = set()
        inline_blocks = None
        out: list[ImageElement] = []
        try:
            infos = page.get_image_info(xrefs=True)
        except Exception as exc:
            return [], [f"Không liệt kê được ảnh: {exc}"]

        for n, info in enumerate(infos):
            bbox = Rect.of(info["bbox"])
            if bbox.width < 0.5 or bbox.height < 0.5 or page_rect.intersect(bbox) is None:
                continue
            matrix = tuple(info.get("transform") or (bbox.width, 0, 0, bbox.height, bbox.x0, bbox.y0))
            z = self._match_z(bbox, image_log, used, default=10_000 + n)
            xref = info.get("xref", 0)
            dec: _Decoded | None = None
            if xref:
                dec = self._decode_xref(doc, xref)
                key = (xref, tuple(round(v, 2) for v in matrix[:4]), round(bbox.width), round(bbox.height))
            else:
                if inline_blocks is None:
                    inline_blocks = self._inline_blocks(page)
                dec = self._decode_inline(inline_blocks, bbox)
                key = ("inline", page.number, n)
            if dec is None:
                dec = self._render_region(page, bbox)
                warnings.append(f"Ảnh tại {tuple(round(v) for v in bbox.as_tuple())} được chụp lại từ trang.")
                key = ("region", page.number, n)
                matrix = (1, 0, 0, 1, 0, 0)
            rel, digest, w, h, alpha = self._store(key, dec, matrix, bbox)
            out.append(ImageElement(bbox=bbox, file=rel, pixel_width=w, pixel_height=h,
                                    has_alpha=alpha, z=z, role=ImageRole.CONTENT, digest=digest))
        return out, warnings

    @staticmethod
    def _match_z(bbox: Rect, image_log, used: set[int], default: int) -> int:
        best, best_i = 0.0, None
        for i, r in image_log:
            if i in used:
                continue
            score = bbox.iou(r)
            if score > best:
                best, best_i = score, i
        if best_i is not None and best > 0.5:
            used.add(best_i)
            return best_i
        return default

    @staticmethod
    def _inline_blocks(page: pymupdf.Page) -> list[dict]:
        try:
            d = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_IMAGES)
            return [b for b in d["blocks"] if b.get("type") == 1]
        except Exception:
            return []

    @staticmethod
    def _decode_inline(blocks: list[dict], bbox: Rect) -> _Decoded | None:
        for b in blocks:
            if Rect.of(b["bbox"]).iou(bbox) > 0.8 and b.get("image"):
                try:
                    pix = pymupdf.Pixmap(b["image"])
                    if pix.colorspace is None or pix.n - pix.alpha not in (1, 3):
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    img = _pix_to_pil(pix)
                    mask = b.get("mask")
                    if mask:
                        mp = pymupdf.Pixmap(mask)
                        alpha = Image.frombytes("L", (mp.width, mp.height), mp.samples[:mp.width * mp.height])
                        img = img.convert("RGBA")
                        img.putalpha(alpha.resize(img.size))
                    return _Decoded(img, None)
                except Exception:
                    return None
        return None

    @staticmethod
    def _render_region(page: pymupdf.Page, bbox: Rect) -> _Decoded:
        clip = pymupdf.Rect(*bbox.as_tuple()) & page.rect
        pix = page.get_pixmap(clip=clip, dpi=150, alpha=False)
        return _Decoded(_pix_to_pil(pix), None)
