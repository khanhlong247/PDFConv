from __future__ import annotations

from statistics import median

from ..domain.layout import Align, ParagraphBlock, ParagraphKind, Row
from ..domain.text import LIST_MARKER

LINE_FACTOR = 1.17


def build_paragraphs(rows: list[Row], x0: float, x1: float) -> list[ParagraphBlock]:
    width = max(x1 - x0, 1.0)
    paras: list[ParagraphBlock] = []
    cur: list[Row] = []

    def close():
        if cur:
            paras.append(_finish(list(cur), x0, x1))
            cur.clear()

    for row in rows:
        if not row.is_simple:
            close()
            paras.append(_finish([row], x0, x1))
            continue
        if cur and _continues(cur, row, x1, width):
            cur.append(row)
        else:
            close()
            cur.append(row)
    close()
    return paras


def _continues(cur: list[Row], row: Row, x1: float, width: float) -> bool:
    prev = cur[-1]
    size = prev.size
    if abs(row.size - size) > 0.6:
        return False
    gap = row.baseline - prev.baseline
    if not (0.9 * size <= gap <= 1.8 * size):
        return False
    if len(cur) >= 2 and abs(gap - (cur[-1].baseline - cur[-2].baseline)) > 0.25 * size:
        return False

    first_word = row.text.split(" ", 1)[0]
    word_w = 0.5 * size * max(len(first_word), 1) + 0.3 * size
    if prev.x1 < x1 - max(2.5 * size, 0.08 * width) and prev.x1 + word_w < x1 - 1:
        return False
    if LIST_MARKER.match(row.text):
        return False
    if len(cur) >= 2:
        left = cur[1].x0
        return abs(row.x0 - left) <= max(2.0, 0.3 * size)

    return -6 * size <= row.x0 - cur[0].x0 <= 4 * size


def _finish(rows: list[Row], x0: float, x1: float) -> ParagraphBlock:
    width = max(x1 - x0, 1.0)
    size = max(r.size for r in rows)
    if len(rows) >= 2:
        lh = median(b.baseline - a.baseline for a, b in zip(rows, rows[1:]))
    else:
        lh = LINE_FACTOR * size
    lh = max(lh, 1.0 * size)
    if not rows[0].is_simple:
        return ParagraphBlock(ParagraphKind.TABBED, rows, Align.LEFT, 0.0, 0.0, lh)

    if len(rows) == 1:
        r = rows[0]
        center_off = (r.x0 + r.x1) / 2 - (x0 + x1) / 2
        if abs(center_off) <= max(3.0, 0.02 * width) and r.x0 - x0 > 0.08 * width:
            return ParagraphBlock(ParagraphKind.TEXT, rows, Align.CENTER, 0.0, 0.0, lh, shift=center_off)
        if abs(r.x1 - x1) <= max(3.0, 0.015 * width) and r.x0 - x0 > 0.3 * width:
            return ParagraphBlock(ParagraphKind.TEXT, rows, Align.RIGHT, 0.0, 0.0, lh, shift=r.x1 - x1)
        return ParagraphBlock(ParagraphKind.TEXT, rows, Align.LEFT, r.x0 - x0, 0.0, lh)

    left = rows[1].x0 - x0
    first = rows[0].x0 - rows[1].x0
    rights = [r.x1 for r in rows[:-1]]
    justified = max(rights) - min(rights) <= 2.0 and abs(max(rights) - x1) <= 0.08 * width
    centered = all(abs((r.x0 + r.x1) / 2 - (x0 + x1) / 2) <= max(3.0, 0.02 * width) for r in rows) \
        and min(r.x0 for r in rows) - x0 > 0.05 * width
    if centered:
        off = sum((r.x0 + r.x1) / 2 for r in rows) / len(rows) - (x0 + x1) / 2
        return ParagraphBlock(ParagraphKind.TEXT, rows, Align.CENTER, 0.0, 0.0, lh, shift=off)
    return ParagraphBlock(ParagraphKind.TEXT, rows, Align.JUSTIFY if justified else Align.LEFT,
                          left, first, lh)
