from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from ..renderers.base import OutputFormat


class LatexMode(str, Enum):
    EXACT = "exact"
    FLOW = "flow"


class ConversionOptions(BaseModel):
    formats: list[OutputFormat] = Field(default_factory=lambda: [OutputFormat.LATEX, OutputFormat.DOCX])
    latex_mode: LatexMode = LatexMode.EXACT
    compile_latex: bool = True
    preview_docx: bool = True
    ocr: bool = False
    ocr_language: str = "vie+eng"
    password: str | None = None
    max_pages: int | None = Field(default=None, ge=1)
    detect_tables: bool = True
    detect_columns: bool = True

    @field_validator("formats")
    @classmethod
    def _non_empty(cls, v: list[OutputFormat]) -> list[OutputFormat]:
        if not v:
            raise ValueError("Cần chọn ít nhất một định dạng đầu ra.")
        return list(dict.fromkeys(v))

    @field_validator("ocr_language")
    @classmethod
    def _lang(cls, v: str) -> str:
        v = v.strip() or "eng"
        if not all(part.isalnum() or "_" in part for part in v.split("+")):
            raise ValueError("Mã ngôn ngữ OCR không hợp lệ (ví dụ: vie+eng).")
        return v

    def public(self) -> dict:
        d = self.model_dump(mode="json")
        d["password"] = "***" if self.password else None
        return d


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Artifact(BaseModel):
    kind: str
    path: str
    label: str
    size: int = 0


class PageReport(BaseModel):
    index: int
    width: float
    height: float
    text_lines: int
    images: int
    shapes: int
    tables: int
    columns: int = 1
    scanned: bool = False
    ocr: bool = False
    complex_graphics: bool = False
    warnings: list[str] = Field(default_factory=list)


class Preview(BaseModel):
    page: int
    original: str | None = None
    latex: str | None = None
    docx: str | None = None


class ConversionReport(BaseModel):
    source_kind: str = "pdf"
    total_pages: int = 0
    processed_pages: int = 0
    pages: list[PageReport] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    fidelity: dict[str, list[float]] = Field(default_factory=dict)
    previews: list[Preview] = Field(default_factory=list)
    latex_log: str | None = None
    docx_log: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(BaseModel):
    id: str
    filename: str
    stem: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    state: JobState = JobState.QUEUED
    progress: int = 0
    message: str = "Đang chờ"
    options: dict = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    report: ConversionReport | None = None
    error: str | None = None
