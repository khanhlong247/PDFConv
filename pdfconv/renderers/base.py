from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..domain.layout import LayoutDocument


class OutputFormat(str, Enum):
    LATEX = "latex"
    DOCX = "docx"


@dataclass(slots=True)
class RenderContext:
    output_dir: Path
    asset_root: Path
    stem: str


@dataclass(slots=True)
class RenderOutput:
    main_file: Path
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DocumentRenderer(ABC):
    format: OutputFormat

    @abstractmethod
    def render(self, layout: LayoutDocument, ctx: RenderContext) -> RenderOutput:
