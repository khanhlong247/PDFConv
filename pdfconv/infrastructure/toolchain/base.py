from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ToolResult:
    success: bool
    pdf_path: Path | None = None
    log: str = ""
    engine: str = ""


@dataclass(slots=True)
class Capabilities:
    latex: bool = False
    docx_pdf: bool = False
    latex_engine: str = ""
    docx_engine: str = ""
    details: dict[str, str] = field(default_factory=dict)


class Toolchain(ABC):
    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def compile_latex(self, project_dir: Path, main_tex: str, timeout: int) -> ToolResult: ...

    @abstractmethod
    def docx_to_pdf(self, docx_path: Path, out_dir: Path, timeout: int) -> ToolResult: ...


def tail(text: str, n: int = 12000) -> str:
    return text if len(text) <= n else "…\n" + text[-n:]
