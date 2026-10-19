from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import Capabilities, Toolchain, ToolResult, tail


def _run(cmd: list[str], cwd: Path, timeout: int, env: dict | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, env=env,
                              stdin=subprocess.DEVNULL)
        out = (proc.stdout or b"").decode("utf-8", "replace") + (proc.stderr or b"").decode("utf-8", "replace")
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return -1, f"Quá thời gian {timeout}s: {' '.join(cmd[:2])}"
    except OSError as exc:
        return -1, f"Không chạy được {cmd[0]}: {exc}"


class LocalToolchain(Toolchain):
    def __init__(self, enable_word: bool = True):
        self.xelatex = shutil.which("xelatex")
        self.soffice = shutil.which("soffice") or shutil.which("libreoffice")
        self.word = enable_word and sys.platform == "win32" and self._has_word()

    @staticmethod
    def _has_word() -> bool:
        try:
            import winreg
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID").Close()
            return True
        except OSError:
            return False

    def capabilities(self) -> Capabilities:
        docx_engine = "libreoffice" if self.soffice else ("msword" if self.word else "")
        return Capabilities(latex=bool(self.xelatex), docx_pdf=bool(docx_engine),
                            latex_engine="xelatex" if self.xelatex else "", docx_engine=docx_engine,
                            details={"xelatex": self.xelatex or "", "soffice": self.soffice or ""})

    def compile_latex(self, project_dir: Path, main_tex: str, timeout: int) -> ToolResult:
        if not self.xelatex:
            return ToolResult(False, log="Không tìm thấy xelatex trên máy chủ.")
        cmd = [self.xelatex, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape",
               "-file-line-error", main_tex]
        env = dict(os.environ)
        env.setdefault("TEXMFVAR", str(Path(tempfile.gettempdir()) / "pdfconv-texmf-var"))
        code, out = _run(cmd, project_dir, timeout, env)
        pdf = project_dir / (Path(main_tex).stem + ".pdf")
        log_file = project_dir / (Path(main_tex).stem + ".log")
        log = log_file.read_text("utf-8", "replace") if log_file.exists() else out
        ok = code == 0 and pdf.exists()
        return ToolResult(ok, pdf if pdf.exists() else None, tail(log), "xelatex")

    def docx_to_pdf(self, docx_path: Path, out_dir: Path, timeout: int) -> ToolResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / (docx_path.stem + ".pdf")
        if self.soffice:
            profile = Path(tempfile.gettempdir()) / "pdfconv-lo-profile"
            cmd = [self.soffice, f"-env:UserInstallation=file:///{profile.as_posix().lstrip('/')}",
                   "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(out_dir),
                   str(docx_path)]
            code, out = _run(cmd, out_dir, timeout)
            return ToolResult(target.exists(), target if target.exists() else None, tail(out), "libreoffice")
        if self.word:
            script = (
                "$ErrorActionPreference='Stop';"
                "$w=New-Object -ComObject Word.Application;$w.Visible=$false;$w.DisplayAlerts=0;"
                "try{$d=$w.Documents.Open($env:PDFCONV_SRC,$false,$true);"
                "$d.ExportAsFixedFormat($env:PDFCONV_DST,17);$d.Close(0)}finally{$w.Quit()}")
            env = dict(os.environ, PDFCONV_SRC=str(docx_path.resolve()), PDFCONV_DST=str(target.resolve()))
            code, out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             out_dir, timeout, env)
            return ToolResult(target.exists(), target if target.exists() else None, tail(out), "msword")
        return ToolResult(False, log="Máy chủ không có LibreOffice/Word để chuyển DOCX sang PDF.")
