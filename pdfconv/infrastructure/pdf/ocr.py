from __future__ import annotations

import glob
import logging
import os
import shutil

import pymupdf

log = logging.getLogger(__name__)

_TESSDATA_CANDIDATES = [
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tessdata",
    "/usr/local/share/tessdata",
    r"C:\Program Files\Tesseract-OCR\tessdata",
]


class OcrEngine:
    def __init__(self, tessdata: str | None = None):
        self.tessdata = tessdata or os.environ.get("TESSDATA_PREFIX") or self._discover()

    @staticmethod
    def _discover() -> str | None:
        try:
            found = pymupdf.get_tessdata()
            if found:
                return found
        except Exception:  # noqa: BLE001
            pass
        for c in _TESSDATA_CANDIDATES:
            if glob.glob(os.path.join(c, "*.traineddata")):
                return c
        return None

    @property
    def available(self) -> bool:
        return bool(self.tessdata and glob.glob(os.path.join(self.tessdata, "*.traineddata")))

    @property
    def binary(self) -> str | None:
        return shutil.which("tesseract")

    def languages(self) -> list[str]:
        if not self.tessdata:
            return []
        return sorted(os.path.basename(p)[:-12] for p in glob.glob(os.path.join(self.tessdata, "*.traineddata")))

    def resolve_language(self, wanted: str) -> str:
        have = set(self.languages())
        langs = [lang for lang in wanted.split("+") if lang in have]
        return "+".join(langs) or ("eng" if "eng" in have else wanted)

    def textpage(self, page: pymupdf.Page, language: str, dpi: int):
        return page.get_textpage_ocr(language=self.resolve_language(language), dpi=dpi, full=True,
                                     tessdata=self.tessdata)
