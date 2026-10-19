from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"PDFCONV_{name}", default)


def _bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    max_upload_mb: int
    max_pages: int
    toolchain_url: str | None
    toolchain_timeout: int
    workers: int
    preview_dpi: int
    vector_dpi: int
    enable_word: bool
    job_ttl_hours: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(_env("DATA_DIR", "./data")).resolve(),
            host=_env("HOST", "127.0.0.1"),
            port=int(_env("PORT", "8000")),
            max_upload_mb=int(_env("MAX_UPLOAD_MB", "100")),
            max_pages=int(_env("MAX_PAGES", "300")),
            toolchain_url=_env("TOOLCHAIN_URL", "") or None,
            toolchain_timeout=int(_env("TOOLCHAIN_TIMEOUT", "240")),
            workers=max(1, int(_env("WORKERS", "1"))),
            preview_dpi=int(_env("PREVIEW_DPI", "72")),
            vector_dpi=int(_env("VECTOR_DPI", "150")),
            enable_word=_bool("ENABLE_WORD", True),
            job_ttl_hours=int(_env("JOB_TTL_HOURS", "72")),
        )
