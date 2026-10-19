from __future__ import annotations

from ..domain.models import TextLine

BIN = 2.0


def find_gutters(lines: list[TextLine], x0: float, x1: float, min_lines: int = 6,
                 max_columns: int = 3) -> list[tuple[float, float]]:

    gutters = _find(lines, x0, x1, min_lines)
    if not gutters:
        return []
    g0, g1 = gutters[0]
    out = [(g0, g1)]
    if max_columns > 2:
        left = [ln for ln in lines if ln.bbox.x1 <= g0 + 1]
        right = [ln for ln in lines if ln.bbox.x0 >= g1 - 1]
        sub = _find(left, x0, g0, min_lines) or _find(right, g1, x1, min_lines)
        if sub:
            out.append(sub[0])
    return sorted(out)


def _find(lines: list[TextLine], x0: float, x1: float, min_lines: int) -> list[tuple[float, float]]:
    hl = [ln for ln in lines if ln.is_horizontal]
    if len(hl) < 2 * min_lines or x1 - x0 < 100:
        return []
    nb = int((x1 - x0) / BIN) + 1
    cover = [0] * nb
    for ln in hl:
        i0 = max(0, int((ln.bbox.x0 - x0) / BIN))
        i1 = min(nb - 1, int((ln.bbox.x1 - x0) / BIN))
        for i in range(i0, i1 + 1):
            cover[i] += 1
    allowed = max(1, int(0.04 * len(hl)))
    lo, hi = int(0.15 * nb), int(0.85 * nb)
    best = None
    i = lo
    while i < hi:
        if cover[i] <= allowed:
            j = i
            while j < hi and cover[j] <= allowed:
                j += 1
            if best is None or (j - i) > (best[1] - best[0]):
                best = (i, j)
            i = j
        else:
            i += 1
    if best is None or (best[1] - best[0]) * BIN < 8:
        return []
    g0, g1 = x0 + best[0] * BIN, x0 + best[1] * BIN
    left = [ln for ln in hl if ln.bbox.x1 <= g0 + 1]
    right = [ln for ln in hl if ln.bbox.x0 >= g1 - 1]
    if len(left) < min_lines or len(right) < min_lines:
        return []
    paired = sum(1 for a in left if any(a.bbox.v_overlap(b.bbox) > 0 for b in right))
    if paired < 3:
        return []
    return [(g0, g1)]
