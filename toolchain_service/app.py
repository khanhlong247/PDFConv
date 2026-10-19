from __future__ import annotations

import base64
import io
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from pdfconv.infrastructure.toolchain.local import LocalToolchain

MAX_BYTES = 200 * 1024 * 1024
MAX_TIMEOUT = 900

app = FastAPI(title="pdfconv toolchain", version="1.0")
tool = LocalToolchain(enable_word=False)


def _result(res) -> dict:
    pdf = base64.b64encode(res.pdf_path.read_bytes()).decode() if res.pdf_path and res.pdf_path.exists() else None
    return {"success": res.success, "log": res.log, "engine": res.engine, "pdf": pdf}


def _safe_extract(data: bytes, dest: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        total = 0
        for info in z.infolist():
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts:
                raise HTTPException(400, f"Đường dẫn không hợp lệ trong zip: {info.filename}")
            total += info.file_size
            if total > MAX_BYTES:
                raise HTTPException(413, "Dự án giải nén quá lớn.")
        z.extractall(dest)


@app.get("/health")
def health():
    caps = tool.capabilities()
    return {"latex": caps.latex, "docx_pdf": caps.docx_pdf, "latex_engine": caps.latex_engine,
            "docx_engine": caps.docx_engine}


@app.post("/latex")
async def compile_latex(archive: UploadFile = File(...), main: str = Form(...), timeout: int = Form(240)):
    if "/" in main or "\\" in main or not main.endswith(".tex"):
        raise HTTPException(400, "Tên file chính không hợp lệ.")
    data = await archive.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File quá lớn.")
    with tempfile.TemporaryDirectory(prefix="tex-") as tmp:
        work = Path(tmp)
        _safe_extract(data, work)
        if not (work / main).exists():
            raise HTTPException(400, f"Không thấy {main} trong gói.")
        return _result(tool.compile_latex(work, main, min(timeout, MAX_TIMEOUT)))


@app.post("/docx-to-pdf")
async def docx_to_pdf(file: UploadFile = File(...), timeout: int = Form(240)):
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File quá lớn.")
    with tempfile.TemporaryDirectory(prefix="docx-") as tmp:
        src = Path(tmp) / "document.docx"
        src.write_bytes(data)
        return _result(tool.docx_to_pdf(src, Path(tmp) / "out", min(timeout, MAX_TIMEOUT)))
