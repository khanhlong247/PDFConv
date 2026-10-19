from __future__ import annotations

import base64
import io
import time
import zipfile
from pathlib import Path

import httpx

from .base import Capabilities, Toolchain, ToolResult


class RemoteToolchain(Toolchain):
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._caps: Capabilities | None = None
        self._caps_at = 0.0

    def capabilities(self) -> Capabilities:
        if self._caps is not None and time.monotonic() - self._caps_at < 30:
            return self._caps
        self._caps_at = time.monotonic()
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=5)
            r.raise_for_status()
            data = r.json()
            self._caps = Capabilities(latex=data.get("latex", False), docx_pdf=data.get("docx_pdf", False),
                                      latex_engine=data.get("latex_engine", ""),
                                      docx_engine=data.get("docx_engine", ""),
                                      details={"url": self.base_url})
        except Exception as exc:
            self._caps = Capabilities(details={"url": self.base_url, "error": str(exc)})
        return self._caps

    @staticmethod
    def _decode(data: dict, out: Path, engine: str) -> ToolResult:
        if data.get("pdf"):
            out.write_bytes(base64.b64decode(data["pdf"]))
            return ToolResult(bool(data.get("success")), out, data.get("log", ""), engine)
        return ToolResult(False, None, data.get("log", ""), engine)

    def compile_latex(self, project_dir: Path, main_tex: str, timeout: int) -> ToolResult:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in project_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() not in (".pdf", ".log", ".aux"):
                    z.write(p, p.relative_to(project_dir).as_posix())
        try:
            r = httpx.post(f"{self.base_url}/latex", data={"main": main_tex, "timeout": str(timeout)},
                           files={"archive": ("project.zip", buf.getvalue(), "application/zip")},
                           timeout=timeout + 30)
            r.raise_for_status()
        except Exception as exc:
            return ToolResult(False, log=f"Lỗi gọi dịch vụ biên dịch: {exc}", engine="remote")
        res = self._decode(r.json(), project_dir / (Path(main_tex).stem + ".pdf"), "remote-xelatex")
        (project_dir / (Path(main_tex).stem + ".log")).write_text(res.log, "utf-8")
        return res

    def docx_to_pdf(self, docx_path: Path, out_dir: Path, timeout: int) -> ToolResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            with docx_path.open("rb") as fh:
                r = httpx.post(f"{self.base_url}/docx-to-pdf", data={"timeout": str(timeout)},
                               files={"file": (docx_path.name, fh.read(),
                                               "application/vnd.openxmlformats-officedocument."
                                               "wordprocessingml.document")},
                               timeout=timeout + 30)
            r.raise_for_status()
        except Exception as exc:
            return ToolResult(False, log=f"Lỗi gọi dịch vụ chuyển DOCX: {exc}", engine="remote")
        return self._decode(r.json(), out_dir / (docx_path.stem + ".pdf"), "remote-libreoffice")


class CompositeToolchain(Toolchain):

    def __init__(self, local: Toolchain, remote: Toolchain | None):
        self.local = local
        self.remote = remote

    def _pick(self, attr: str) -> Toolchain | None:
        if getattr(self.local.capabilities(), attr):
            return self.local
        if self.remote is not None and getattr(self.remote.capabilities(), attr):
            return self.remote
        return None

    def capabilities(self) -> Capabilities:
        lc = self.local.capabilities()
        rc = self.remote.capabilities() if self.remote else Capabilities()
        return Capabilities(
            latex=lc.latex or rc.latex, docx_pdf=lc.docx_pdf or rc.docx_pdf,
            latex_engine=lc.latex_engine or (f"remote:{rc.latex_engine}" if rc.latex else ""),
            docx_engine=lc.docx_engine or (f"remote:{rc.docx_engine}" if rc.docx_pdf else ""),
            details={**rc.details, **{k: v for k, v in lc.details.items() if v}})

    def compile_latex(self, project_dir: Path, main_tex: str, timeout: int) -> ToolResult:
        tc = self._pick("latex")
        if tc is None:
            return ToolResult(False, log="Không có trình biên dịch LaTeX (cài TeX Live/MiKTeX hoặc chạy docker compose).")
        return tc.compile_latex(project_dir, main_tex, timeout)

    def docx_to_pdf(self, docx_path: Path, out_dir: Path, timeout: int) -> ToolResult:
        tc = self._pick("docx_pdf")
        if tc is None:
            return ToolResult(False, log="Không có LibreOffice/Word để xem trước DOCX.")
        return tc.docx_to_pdf(docx_path, out_dir, timeout)
