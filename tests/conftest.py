from __future__ import annotations

import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pdfconv.config import Settings  # noqa: E402

from . import fixtures  # noqa: E402

HAS_XELATEX = shutil.which("xelatex") is not None


@pytest.fixture(scope="session")
def case_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("cases")


@pytest.fixture(scope="session")
def cases(case_dir) -> dict[str, Path]:
    out = {}
    for name, fn in fixtures.ALL_CASES.items():
        out[name] = fn(case_dir / f"{name}.pdf")
    out["encrypted"] = fixtures.encrypted(case_dir / "encrypted.pdf")
    out["png_image"] = fixtures.png_image(case_dir / "picture.png")
    return out


@pytest.fixture()
def settings(tmp_path) -> Settings:
    s = Settings.from_env()
    return replace(s, data_dir=tmp_path / "data", toolchain_url=None, enable_word=False)
