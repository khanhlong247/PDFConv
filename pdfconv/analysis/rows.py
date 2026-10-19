from __future__ import annotations

from collections import Counter

from ..domain.layout import Row, Run, Segment, SegmentKind
from ..domain.models import TextLine, TextSpan
from ..domain.text import LEADER_CHARS


def build_rows(lines: list[TextLine]) -> list[Row]:
    ordered = sorted(lines, key=lambda ln: (round(ln.baseline, 1), ln.bbox.x0))
    groups: list[dict] = []
    for ln in ordered:
        if not ln.spans:
            continue
        size = max(ln.size, 1.0)
        best, best_d = None, 1e9
        if ln.is_horizontal:
            for g in reversed(groups[-8:]):
                if not g["horizontal"]:
                    continue
                d = abs(ln.baseline - g["baseline"])
                gap_x = min((max(o.bbox.x0 - ln.bbox.x1, ln.bbox.x0 - o.bbox.x1) for o in g["lines"]),
                            default=0)
                similar = min(size, g["size"]) / max(size, g["size"]) >= 0.7
                same_line = (d <= 0.45 * min(size, g["size"])
                             or (similar and d <= 0.75 * min(size, g["size"]) and gap_x >= 0.8 * size))
                script = (ln.size < 0.85 * g["size"] and g["top"] <= ln.bbox.cy <= g["bottom"])
                if not (same_line or script):
                    continue
                overlap = max((ln.bbox.h_overlap(o.bbox) for o in g["lines"]), default=0)
                if overlap > 0.5 * min(ln.bbox.width, min(o.bbox.width for o in g["lines"])):
                    continue
                if d < best_d:
                    best, best_d = g, d
        if best is None:
            groups.append({"lines": [ln], "baseline": ln.baseline, "size": size,
                           "top": ln.bbox.y0, "bottom": ln.bbox.y1, "horizontal": ln.is_horizontal})
        else:
            best["lines"].append(ln)
            if size > best["size"]:
                best["size"], best["baseline"] = size, ln.baseline
            best["top"] = min(best["top"], ln.bbox.y0)
            best["bottom"] = max(best["bottom"], ln.bbox.y1)

    rows: list[Row] = []
    for g in groups:
        spans = sorted((s for ln in g["lines"] for s in ln.spans), key=lambda s: s.bbox.x0)
        segs = build_segments(spans, g["size"], g["baseline"])
        if segs:
            rows.append(Row(segments=segs, top=g["top"], bottom=g["bottom"],
                            baseline=g["baseline"], size=g["size"]))
    rows.sort(key=lambda r: (r.baseline, r.x0))
    return rows


def _leader_runs(glyphs: list[tuple]) -> list[tuple[int, int, str]]:
    out = []
    n = len(glyphs)
    i = 0
    while i < n:
        c = glyphs[i][0].char
        if c in LEADER_CHARS or c == "-":
            j = i
            chars = []
            while j < n:
                cj = glyphs[j][0].char
                if cj in LEADER_CHARS or cj == "-":
                    chars.append(cj)
                    j += 1
                elif cj == " " and j + 1 < n and (glyphs[j + 1][0].char in LEADER_CHARS
                                                   or glyphs[j + 1][0].char == "-"):
                    j += 1
                else:
                    break
            cnt = Counter("." if ch in ".…·‥" else ch for ch in chars)
            kind, num = cnt.most_common(1)[0]
            weight = num + 2 * chars.count("…")
            if (kind == "." and weight >= 4) or (kind == "_" and num >= 3) or (kind == "-" and num >= 8):
                out.append((i, j - 1, kind))
            i = max(j, i + 1)
        else:
            i += 1
    return out


def build_segments(spans: list[TextSpan], row_size: float, baseline: float) -> list[Segment]:
    glyphs: list[tuple] = [(g, s) for s in spans for g in s.glyphs]
    glyphs.sort(key=lambda gs: gs[0].x0)
    if not glyphs:
        return []
    leaders = _leader_runs(glyphs)
    leader_at = {a: (b, k) for a, b, k in leaders}

    segments: list[Segment] = []
    cur: list[tuple] = []

    def flush():
        seg = _text_segment(cur, row_size, baseline)
        if seg:
            segments.append(seg)
        cur.clear()

    i = 0
    last_x1 = None
    while i < len(glyphs):
        if i in leader_at:
            flush()
            j, kind = leader_at[i]
            g0, s0 = glyphs[i]
            g1 = glyphs[j][0]
            original = "".join(glyphs[k][0].char for k in range(i, j + 1))
            segments.append(Segment(SegmentKind.LEADER, g0.x0, g1.x1,
                                    [Run(original, s0.font, s0.size, s0.color)], leader_char=kind))
            last_x1 = g1.x1
            i = j + 1
            continue
        g, s = glyphs[i]
        if g.char != " " and last_x1 is not None and cur:
            gap = g.x0 - last_x1
            if gap > max(1.0 * max(s.size, row_size * 0.6), 5.0):
                flush()
        cur.append((g, s))
        if g.char != " ":
            last_x1 = g.x1
        i += 1
    flush()
    return segments


def _text_segment(items: list[tuple], row_size: float, baseline: float) -> Segment | None:
    core = [it for it in items]
    while core and core[0][0].char == " ":
        core.pop(0)
    while core and core[-1][0].char == " ":
        core.pop()
    if not core:
        return None
    runs: list[Run] = []
    prev_g = None
    prev_s = None
    for g, s in core:
        sup = s.superscript or (s.size < 0.8 * row_size and s.origin.y < baseline - 0.15 * row_size)
        text = g.char
        if prev_g is not None and s is not prev_s and g.char != " " and prev_g.char != " ":
            if g.x0 - prev_g.x1 > 0.15 * s.size:
                text = " " + text
        run = Run(text, s.font, round(s.size, 2), s.color, sup)
        if runs and runs[-1].same_style(run):
            runs[-1].text += text
        else:
            if text.startswith(" ") and runs:
                runs[-1].text += " "
                run.text = text[1:]
            runs.append(run)
        prev_g, prev_s = g, s
    nonspace = [g for g, _ in core if g.char != " "]
    return Segment(SegmentKind.TEXT, nonspace[0].x0, nonspace[-1].x1, runs)
