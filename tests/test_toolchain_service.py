from __future__ import annotations

import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from toolchain_service.app import app

from .conftest import HAS_XELATEX

client = TestClient(app)
TEX = r"""\documentclass{article}\usepackage{fontspec}\begin{document}Xin chào Việt Nam\end{document}"""


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


def test_health():
    assert set(client.get("/health").json()) >= {"latex", "docx_pdf"}


@pytest.mark.skipif(not HAS_XELATEX, reason="cần xelatex")
def test_compile_latex():
    r = client.post("/latex", data={"main": "main.tex"},
                    files={"archive": ("p.zip", _zip({"main.tex": TEX}), "application/zip")})
    data = r.json()
    assert data["success"], data["log"][-2000:]
    assert base64.b64decode(data["pdf"]).startswith(b"%PDF")


def test_rejects_zip_slip_and_bad_main():
    r = client.post("/latex", data={"main": "main.tex"},
                    files={"archive": ("p.zip", _zip({"../evil.tex": TEX}), "application/zip")})
    assert r.status_code == 400
    r = client.post("/latex", data={"main": "../x.tex"},
                    files={"archive": ("p.zip", _zip({"main.tex": TEX}), "application/zip")})
    assert r.status_code == 400
