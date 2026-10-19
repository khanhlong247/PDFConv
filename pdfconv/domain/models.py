from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from .geometry import Point, Rect


class GenericFamily(str, Enum):
    SERIF = "serif"
    SANS = "sans"
    MONO = "mono"
    SYMBOL = "symbol"


@dataclass(frozen=True, slots=True)
class Color:
    r: float
    g: float
    b: float

    @classmethod
    def from_int(cls, value: int) -> "Color":
        return cls(((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255)

    @classmethod
    def from_seq(cls, seq: Sequence[float] | None) -> "Color | None":
        if seq is None:
            return None
        vals = [min(1.0, max(0.0, float(v))) for v in seq]
        if len(vals) == 1:
            return cls(vals[0], vals[0], vals[0])
        if len(vals) == 3:
            return cls(*vals)
        if len(vals) == 4:
            c, m, y, k = vals
            return cls((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
        return None

    @property
    def rgb255(self) -> tuple[int, int, int]:
        return (round(self.r * 255), round(self.g * 255), round(self.b * 255))

    @property
    def hex(self) -> str:
        return "%02X%02X%02X" % self.rgb255

    @property
    def is_black(self) -> bool:
        return max(self.rgb255) <= 16

    @property
    def is_white(self) -> bool:
        return min(self.rgb255) >= 250


BLACK = Color(0, 0, 0)


@dataclass(frozen=True, slots=True)
class FontInfo:
    family: str
    generic: GenericFamily
    bold: bool
    italic: bool
    raw_name: str = ""


@dataclass(slots=True)
class Glyph:
    char: str
    x0: float
    x1: float


@dataclass(slots=True)
class TextSpan:
    text: str
    bbox: Rect
    origin: Point
    font: FontInfo
    size: float
    color: Color
    glyphs: list[Glyph] = field(default_factory=list)
    superscript: bool = False
    alpha: float = 1.0


@dataclass(slots=True)
class TextLine:
    spans: list[TextSpan]
    bbox: Rect
    angle: float = 0.0
    vertical: bool = False

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def baseline(self) -> float:
        return self.spans[0].origin.y if self.spans else self.bbox.y1

    @property
    def size(self) -> float:
        return max((s.size for s in self.spans), default=0.0)

    @property
    def is_horizontal(self) -> bool:
        return not self.vertical and abs(self.angle) < 0.5


class ImageRole(str, Enum):
    CONTENT = "content"
    BACKGROUND = "background"
    PAGE_SCAN = "page_scan"
    VECTOR_LAYER = "vector_layer"


@dataclass(slots=True)
class ImageElement:
    bbox: Rect
    file: str
    pixel_width: int
    pixel_height: int
    has_alpha: bool = False
    z: int = 0
    role: ImageRole = ImageRole.CONTENT
    digest: str = ""


@dataclass(frozen=True, slots=True)
class PathSegment:
    op: str
    points: tuple[Point, ...]


@dataclass(slots=True)
class Shape:
    segments: list[PathSegment]
    bbox: Rect
    stroke: Color | None = None
    fill: Color | None = None
    width: float = 1.0
    dashes: tuple[float, ...] = ()
    dash_phase: float = 0.0
    stroke_opacity: float = 1.0
    fill_opacity: float = 1.0
    close_path: bool = False
    even_odd: bool = False
    line_cap: int = 0
    line_join: int = 0
    z: int = 0


@dataclass(slots=True)
class TableCell:
    row: int
    col: int
    row_span: int
    col_span: int
    bbox: Rect


@dataclass(slots=True)
class TableElement:
    bbox: Rect
    col_edges: list[float]
    row_edges: list[float]
    cells: list[TableCell]

    @property
    def n_rows(self) -> int:
        return len(self.row_edges) - 1

    @property
    def n_cols(self) -> int:
        return len(self.col_edges) - 1


@dataclass(slots=True)
class Page:
    index: int
    width: float
    height: float
    lines: list[TextLine] = field(default_factory=list)
    images: list[ImageElement] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    tables: list[TableElement] = field(default_factory=list)
    vector_layer: ImageElement | None = None
    vector_layer_full: ImageElement | None = None
    complex_graphics: bool = False
    is_scanned: bool = False
    ocr_applied: bool = False
    text_reliable: bool = True
    shape_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def rect(self) -> Rect:
        return Rect(0, 0, self.width, self.height)


@dataclass(slots=True)
class Document:
    name: str
    pages: list[Page]
    metadata: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    total_pages: int = 0

    @property
    def page_count(self) -> int:
        return len(self.pages)


def angle_from_dir(cos_v: float, sin_v: float) -> float:
    ang = -math.degrees(math.atan2(sin_v, cos_v))
    return 0.0 if abs(ang) < 0.5 else round(ang, 2)
