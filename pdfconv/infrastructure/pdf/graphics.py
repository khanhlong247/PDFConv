from __future__ import annotations

import re

import pymupdf

from ...domain.geometry import Point, Rect
from ...domain.models import Color, PathSegment, Shape

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _pt(p) -> Point:
    return Point(float(p.x), float(p.y))


def _parse_dashes(s: str | None) -> tuple[tuple[float, ...], float]:
    if not s:
        return (), 0.0
    inside, _, phase = s.partition("]")
    arr = tuple(float(v) for v in _NUM.findall(inside))
    nums = _NUM.findall(phase)
    if not arr or all(v == 0 for v in arr):
        return (), 0.0
    return arr, float(nums[0]) if nums else 0.0


def _first(v, default=0):
    if v is None:
        return default
    if isinstance(v, (tuple, list)):
        return int(v[0]) if v else default
    return int(v)


class ShapeExtractor:
    def extract(self, drawings: list[dict]) -> list[Shape]:
        shapes: list[Shape] = []
        for dr in drawings:
            segs: list[PathSegment] = []
            for item in dr.get("items", ()):
                op = item[0]
                if op == "l":
                    segs.append(PathSegment("l", (_pt(item[1]), _pt(item[2]))))
                elif op == "c":
                    segs.append(PathSegment("c", tuple(_pt(p) for p in item[1:5])))
                elif op == "re":
                    r = item[1]
                    segs.append(PathSegment("re", (Point(r.x0, r.y0), Point(r.x1, r.y1))))
                elif op == "qu":
                    q = item[1]
                    segs.append(PathSegment("qu", (_pt(q.ul), _pt(q.ur), _pt(q.lr), _pt(q.ll))))
            if not segs:
                continue
            kind = dr.get("type") or ""
            stroke = Color.from_seq(dr.get("color")) if "s" in kind else None
            fill = Color.from_seq(dr.get("fill")) if "f" in kind else None
            if stroke is None and fill is None:
                continue
            dashes, phase = _parse_dashes(dr.get("dashes"))
            width = dr.get("width")
            shapes.append(Shape(
                segments=segs,
                bbox=Rect.of(dr["rect"]),
                stroke=stroke,
                fill=fill,
                width=float(width) if width is not None else 1.0,
                dashes=dashes,
                dash_phase=phase,
                stroke_opacity=float(dr.get("stroke_opacity") or 1.0),
                fill_opacity=float(dr.get("fill_opacity") or 1.0),
                close_path=bool(dr.get("closePath")),
                even_odd=bool(dr.get("even_odd")),
                line_cap=_first(dr.get("lineCap")),
                line_join=_first(dr.get("lineJoin")),
                z=int(dr.get("seqno", 0)),
            ))
        return shapes


def page_drawings(page: pymupdf.Page) -> list[dict]:
    try:
        return page.get_drawings()
    except Exception:
        return []
