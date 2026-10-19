from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def of(cls, seq: Sequence[float]) -> "Rect":
        x0, y0, x1, y1 = (float(v) for v in tuple(seq)[:4])
        return cls(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    @classmethod
    def union_all(cls, rects: Iterable["Rect"]) -> "Rect | None":
        out: Rect | None = None
        for r in rects:
            out = r if out is None else out.union(r)
        return out

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0

    def union(self, o: "Rect") -> "Rect":
        return Rect(min(self.x0, o.x0), min(self.y0, o.y0), max(self.x1, o.x1), max(self.y1, o.y1))

    def intersect(self, o: "Rect") -> "Rect | None":
        r = Rect(max(self.x0, o.x0), max(self.y0, o.y0), min(self.x1, o.x1), min(self.y1, o.y1))
        return None if r.is_empty else r

    def overlap_area(self, o: "Rect") -> float:
        r = self.intersect(o)
        return r.area if r else 0.0

    def h_overlap(self, o: "Rect") -> float:
        return max(0.0, min(self.x1, o.x1) - max(self.x0, o.x0))

    def v_overlap(self, o: "Rect") -> float:
        return max(0.0, min(self.y1, o.y1) - max(self.y0, o.y0))

    def contains_point(self, x: float, y: float, tol: float = 0.0) -> bool:
        return self.x0 - tol <= x <= self.x1 + tol and self.y0 - tol <= y <= self.y1 + tol

    def contains(self, o: "Rect", tol: float = 0.0) -> bool:
        return (o.x0 >= self.x0 - tol and o.y0 >= self.y0 - tol
                and o.x1 <= self.x1 + tol and o.y1 <= self.y1 + tol)

    def expand(self, d: float) -> "Rect":
        return Rect(self.x0 - d, self.y0 - d, self.x1 + d, self.y1 + d)

    def iou(self, o: "Rect") -> float:
        inter = self.overlap_area(o)
        if inter <= 0:
            return 0.0
        return inter / (self.area + o.area - inter)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)
