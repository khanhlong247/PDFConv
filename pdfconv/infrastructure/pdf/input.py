from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ...domain.errors import UnsupportedInputError

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".jxr", ".jpx", ".jp2",
             ".pnm", ".pgm", ".pbm", ".ppm", ".pam", ".psd", ".webp"}
DOC_EXT = {".pdf", ".xps", ".oxps", ".epub", ".cbz", ".fb2", ".svg", ".mobi"}
SUPPORTED_EXT = IMAGE_EXT | DOC_EXT


@dataclass(frozen=True, slots=True)
class NormalizedInput:
    pdf_bytes: bytes
    source_kind: str
    stem: str


def safe_stem(filename: str) -> str:
    stem = Path(filename or "document").stem
    keep = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in stem)
    keep = keep.strip("-.") or "document"
    return keep[:120]


class InputNormalizer:
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes

    def normalize(self, data: bytes, filename: str) -> NormalizedInput:
        if not data:
            raise UnsupportedInputError("File rỗng.")
        if len(data) > self.max_bytes:
            raise UnsupportedInputError(
                f"File quá lớn ({len(data) / 1e6:.1f} MB > {self.max_bytes / 1e6:.0f} MB).")
        ext = Path(filename or "").suffix.lower()
        stem = safe_stem(filename)
        if b"%PDF" in data[:1024]:
            return NormalizedInput(data, "pdf", stem)
        if ext and ext not in SUPPORTED_EXT:
            raise UnsupportedInputError(f"Định dạng '{ext}' không được hỗ trợ.")
        try:
            src = pymupdf.open(stream=data, filetype=ext.lstrip(".") or None)
        except Exception as exc:
            raise UnsupportedInputError(f"Không mở được file: {exc}") from exc
        try:
            if src.is_pdf:
                return NormalizedInput(src.tobytes(), "pdf", stem)
            pdf = src.convert_to_pdf()
        except Exception as exc:
            raise UnsupportedInputError(f"Không chuyển được sang PDF: {exc}") from exc
        finally:
            src.close()
        kind = "image" if ext in IMAGE_EXT else (ext.lstrip(".") or "document")
        return NormalizedInput(pdf, kind, stem)
