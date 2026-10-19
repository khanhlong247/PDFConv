from __future__ import annotations

from ..domain.geometry import Rect
from ..domain.models import Shape

THIN = 2.5
TOL = 3.0


def find_boxes(shapes: list[Shape], max_segments: int = 400) -> list[Rect]:
    horiz: list[tuple[float, float, float]] = []
    vert: list[tuple[float, float, float]] = []
    boxes: list[Rect] = []
    for s in shapes:
        for seg in s.segments:
            if seg.op in ("re", "qu"):
                xs = [p.x for p in seg.points]
                ys = [p.y for p in seg.points]
                r = Rect(min(xs), min(ys), max(xs), max(ys))
                if r.height <= THIN and r.width > 8:
                    horiz.append((r.x0, r.x1, r.cy))
                elif r.width <= THIN and r.height > 8:
                    vert.append((r.y0, r.y1, r.cx))
                elif s.stroke is not None and r.width > 15 and r.height > 10:
                    boxes.append(r)
            elif seg.op == "l" and s.stroke is not None:
                a, b = seg.points
                if abs(a.y - b.y) < 1 and abs(a.x - b.x) > 8:
                    horiz.append((min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2))
                elif abs(a.x - b.x) < 1 and abs(a.y - b.y) > 8:
                    vert.append((min(a.y, b.y), max(a.y, b.y), (a.x + b.x) / 2))
    if len(horiz) <= max_segments and len(vert) <= max_segments:
        horiz.sort(key=lambda h: h[2])
        for i, (tx0, tx1, ty) in enumerate(horiz):
            for bx0, bx1, by in horiz[i + 1:]:
                if by - ty < 10 or abs(bx0 - tx0) > TOL or abs(bx1 - tx1) > TOL:
                    continue
                x0, x1 = (tx0 + bx0) / 2, (tx1 + bx1) / 2
                left = any(abs(vx - x0) <= TOL and vy0 <= ty + TOL and vy1 >= by - TOL for vy0, vy1, vx in vert)
                right = any(abs(vx - x1) <= TOL and vy0 <= ty + TOL and vy1 >= by - TOL for vy0, vy1, vx in vert)
                if left and right:
                    boxes.append(Rect(x0, ty, x1, by))
                    break
    out: list[Rect] = []
    for b in sorted(boxes, key=lambda r: r.area):
        if not any(b.iou(o) > 0.9 for o in out):
            out.append(b)
    return out
