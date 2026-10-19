from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .. import __version__
from ..application.dto import ConversionOptions, Job
from ..container import Container, build_container

log = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"


def create_app(container: Container | None = None) -> FastAPI:
    c = container or build_container()
    app = FastAPI(title="pdfconv", version=__version__,
                  description="Chuyển PDF sang LaTeX và DOCX giữ bố cục, logo và ảnh chìm.")
    app.state.container = c
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": "Dữ liệu không hợp lệ", "errors": exc.errors()})

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "templates" / "index.html", media_type="text/html")

    @app.get("/api/health")
    def health():
        caps = c.toolchain.capabilities()
        return {
            "version": __version__,
            "toolchain": {"latex": caps.latex, "latex_engine": caps.latex_engine,
                          "docx_pdf": caps.docx_pdf, "docx_engine": caps.docx_engine},
            "ocr": {"available": c.ocr.available, "languages": c.ocr.languages()},
            "limits": {"max_upload_mb": c.settings.max_upload_mb, "max_pages": c.settings.max_pages},
        }

    @app.post("/api/jobs", response_model=list[Job], status_code=202)
    async def create_jobs(files: list[UploadFile] = File(...), options: str = Form("{}")):
        try:
            opts = ConversionOptions.model_validate(json.loads(options or "{}"))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise HTTPException(422, f"Tuỳ chọn không hợp lệ: {exc}") from exc
        limit = c.settings.max_upload_mb * 1024 * 1024
        jobs = []
        for f in files:
            data = await f.read(limit + 1)
            if len(data) > limit:
                raise HTTPException(413, f"'{f.filename}' vượt quá {c.settings.max_upload_mb} MB.")
            jobs.append(c.jobs.submit(data, f.filename or "document.pdf", opts))
        return jobs

    @app.get("/api/jobs", response_model=list[Job])
    def list_jobs():
        return c.jobs.list()

    @app.get("/api/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str):
        job = c.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Không tìm thấy job.")
        return job

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str):
        if not c.jobs.delete(job_id):
            raise HTTPException(404, "Không tìm thấy job.")

    @app.get("/api/jobs/{job_id}/files/{rel_path:path}")
    def get_file(job_id: str, rel_path: str, download: bool = False):
        try:
            path = c.repo.resolve_file(job_id, rel_path)
        except KeyError:
            path = None
        if path is None:
            raise HTTPException(404, "Không tìm thấy file.")
        return FileResponse(path, filename=path.name if download else None,
                            content_disposition_type="attachment" if download else "inline")

    return app
