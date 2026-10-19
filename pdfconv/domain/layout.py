from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .geometry import Rect
from .models import Color, Document, FontInfo, ImageElement, Page, TableElement


class Align(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class SegmentKind(str, Enum):
    TEXT = "text"
    LEADER = "leader"


@dataclass(slots=True)
class Run:
    text: str
    font: FontInfo
    size: float
    color: Color
    superscript: bool = False

    def same_style(self, o: "Run") -> bool:
        return (self.font == o.font and abs(self.size - o.size) < 0.05
                and self.color == o.color and self.superscript == o.superscript)


@dataclass(slots=True)
class Segment:
    kind: SegmentKind
    x0: float
    x1: float
    runs: list[Run] = field(default_factory=list)
    leader_char: str = "."

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def size(self) -> float:
        return max((r.size for r in self.runs), default=0.0)


@dataclass(slots=True)
class Row:
    segments: list[Segment]
    top: float
    bottom: float
    baseline: float
    size: float

    @property
    def x0(self) -> float:
        return self.segments[0].x0

    @property
    def x1(self) -> float:
        return self.segments[-1].x1

    @property
    def text(self) -> str:
        return "".join(s.text if s.kind is SegmentKind.TEXT else "…" for s in self.segments)

    @property
    def is_simple(self) -> bool:
        return len(self.segments) == 1 and self.segments[0].kind is SegmentKind.TEXT


class ParagraphKind(str, Enum):
    TEXT = "text"
    TABBED = "tabbed"


@dataclass(slots=True)
class ParagraphBlock:
    kind: ParagraphKind
    rows: list[Row]
    align: Align = Align.LEFT
    left: float = 0.0
    first_indent: float = 0.0
    line_height: float = 12.0
    space_before: float = 0.0
    shift: float = 0.0

    @property
    def top(self) -> float:
        return self.rows[0].baseline - 0.8 * self.line_height

    @property
    def bottom(self) -> float:
        return self.rows[-1].baseline + 0.2 * self.line_height

    @property
    def size(self) -> float:
        return max(r.size for r in self.rows)

    def runs(self) -> list[Run]:
        out: list[Run] = []
        for i, row in enumerate(self.rows):
            seg_runs = [Run(r.text, r.font, r.size, r.color, r.superscript)
                        for r in row.segments[0].runs]
            if not seg_runs:
                continue
            if out:
                prev = out[-1]
                if prev.text.endswith("-") and len(prev.text) > 1 and seg_runs[0].text[:1].islower():
                    prev.text = prev.text[:-1]
                elif not prev.text.endswith(" ") and not seg_runs[0].text.startswith(" "):
                    prev.text += " "
            for r in seg_runs:
                if out and out[-1].same_style(r):
                    out[-1].text += r.text
                else:
                    out.append(r)
        return out


@dataclass(slots=True)
class CellContent:
    row: int
    col: int
    row_span: int
    col_span: int
    bbox: Rect
    paragraphs: list[ParagraphBlock] = field(default_factory=list)
    v_align: str = "top"


@dataclass(slots=True)
class TableBlock:
    table: TableElement
    cells: list[CellContent]
    left: float = 0.0
    space_before: float = 0.0

    @property
    def top(self) -> float:
        return self.table.bbox.y0

    @property
    def bottom(self) -> float:
        return self.table.bbox.y1


@dataclass(slots=True)
class ImageBlock:
    image: ImageElement
    align: Align = Align.LEFT
    left: float = 0.0
    space_before: float = 0.0

    @property
    def top(self) -> float:
        return self.image.bbox.y0

    @property
    def bottom(self) -> float:
        return self.image.bbox.y1


@dataclass(slots=True)
class TextBoxBlock:
    bbox: Rect
    paragraphs: list[ParagraphBlock] = field(default_factory=list)
    v_align: str = "top"


Block = ParagraphBlock | TableBlock | ImageBlock


@dataclass(slots=True)
class Region:
    x0: float
    x1: float
    blocks: list[Block] = field(default_factory=list)

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass(slots=True)
class Band:
    top: float
    bottom: float
    regions: list[Region]
    gutter: float = 0.0

    @property
    def columns(self) -> int:
        return len(self.regions)


@dataclass(slots=True)
class PageGeometry:
    width: float
    height: float
    margin_left: float
    margin_right: float
    margin_top: float
    margin_bottom: float

    @property
    def text_width(self) -> float:
        return self.width - self.margin_left - self.margin_right


@dataclass(slots=True)
class LayoutPage:
    page: Page
    geometry: PageGeometry
    bands: list[Band] = field(default_factory=list)
    anchored: list[ImageElement] = field(default_factory=list)
    vector_layer: ImageElement | None = None
    text_boxes: list[TextBoxBlock] = field(default_factory=list)


@dataclass(slots=True)
class LayoutDocument:
    document: Document
    pages: list[LayoutPage]
