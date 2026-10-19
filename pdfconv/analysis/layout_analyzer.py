from __future__ import annotations

from dataclasses import dataclass

from ..domain.geometry import Rect
from ..domain.layout import (Align, Band, CellContent, ImageBlock, LayoutDocument, LayoutPage,
                             PageGeometry, ParagraphBlock, Region, TableBlock, TextBoxBlock)
from ..domain.models import Document, ImageElement, ImageRole, Page, TableElement, TextLine
from .boxes import find_boxes
from .columns import find_gutters
from .paragraphs import build_paragraphs
from .rows import build_rows

CELL_PAD = 2.0


def _content_in_box(lines: list[TextLine], box: Rect) -> tuple[list[ParagraphBlock], str]:
    rows = build_rows(lines)
    paras = build_paragraphs(rows, box.x0 + CELL_PAD, box.x1 - CELL_PAD)
    if not paras:
        return [], "top"
    cursor = box.y0 + CELL_PAD
    for p in paras:
        p.space_before = max(0.0, p.top - cursor)
        cursor += p.space_before + (p.bottom - p.top)
    top_gap = paras[0].top - box.y0
    bottom_gap = box.y1 - paras[-1].bottom
    v_align = "top"
    if abs(top_gap - bottom_gap) <= max(3.0, 0.25 * box.height):
        v_align = "center"
    elif top_gap > 2 * bottom_gap + 3:
        v_align = "bottom"
    if v_align != "top":
        paras[0].space_before = 0.0
    return paras, v_align


@dataclass(slots=True)
class AnalyzerConfig:
    detect_columns: bool = True
    use_tables: bool = True


@dataclass(slots=True)
class _PageItems:
    flow_lines: list[TextLine]
    tables: list[tuple[TableElement, list[TextLine]]]
    inline_images: list[ImageElement]
    anchored: list[ImageElement]
    boxes: list[tuple[Rect, list[TextLine]]]

    def content_rects(self) -> list[Rect]:
        return ([ln.bbox for ln in self.flow_lines] + [t.bbox for t, _ in self.tables]
                + [im.bbox for im in self.inline_images])



class LayoutAnalyzer:
    def __init__(self, cfg: AnalyzerConfig | None = None):
        self.cfg = cfg or AnalyzerConfig()

    def analyze(self, doc: Document) -> LayoutDocument:
        items = [self._classify(p) for p in doc.pages]
        geoms = self._geometries(doc.pages, items)
        pages = [self._layout_page(p, it, g) for p, it, g in zip(doc.pages, items, geoms)]
        return LayoutDocument(document=doc, pages=pages)

    def _classify(self, page: Page) -> _PageItems:
        tables: list[tuple[TableElement, list[TextLine]]] = []
        remaining = list(page.lines)
        if self.cfg.use_tables:
            for t in page.tables:
                box = t.bbox.expand(1.0)
                inside = [ln for ln in remaining if box.contains_point(ln.bbox.cx, ln.bbox.cy)]
                tables.append((t, inside))
                ids = {id(ln) for ln in inside}
                remaining = [ln for ln in remaining if id(ln) not in ids]

        page_area = page.width * page.height
        boxes: list[tuple[Rect, list[TextLine]]] = []
        for box in find_boxes(page.shapes):
            if box.area > 0.3 * page_area or any(t.bbox.overlap_area(box) > 0 for t, _ in tables):
                continue
            inside = [ln for ln in remaining if box.contains(ln.bbox, tol=1.5)]
            crossing = [ln for ln in remaining if ln not in inside and ln.bbox.overlap_area(box) > 0]
            if not inside or crossing:
                continue
            boxes.append((box, inside))
            ids = {id(ln) for ln in inside}
            remaining = [ln for ln in remaining if id(ln) not in ids]

        inline, anchored = [], []
        for im in page.images:
            if im.role is not ImageRole.CONTENT:
                anchored.append(im)
                continue
            over_text = any(im.bbox.overlap_area(ln.bbox) > 0.3 * min(ln.bbox.area, im.bbox.area)
                            for ln in remaining)
            in_table = any(t.bbox.overlap_area(im.bbox) > 0.3 * im.bbox.area for t, _ in tables)
            beside_text = any(im.bbox.v_overlap(ln.bbox) > 0.3 * max(ln.bbox.height, 1)
                              for ln in remaining)
            if over_text or in_table:
                if im.bbox.area > 0.15 * page_area or over_text:
                    im.role = ImageRole.BACKGROUND
                anchored.append(im)
            elif beside_text:
                anchored.append(im)
            else:
                inline.append(im)
        return _PageItems(remaining, tables, inline, anchored, boxes)

    @staticmethod
    def _geometries(pages: list[Page], items: list[_PageItems]) -> list[PageGeometry]:
        groups: dict[tuple[int, int], list[int]] = {}
        for i, p in enumerate(pages):
            groups.setdefault((round(p.width), round(p.height)), []).append(i)
        out: list[PageGeometry | None] = [None] * len(pages)
        for idxs in groups.values():
            w, h = pages[idxs[0]].width, pages[idxs[0]].height
            rects = [r for i in idxs for r in items[i].content_rects()]
            if rects:
                u = Rect.union_all(rects)
                ml = min(max(u.x0 - 1, 18.0), 144.0)
                mr = min(max(w - u.x1 - 1, 18.0), 144.0)
                mt = min(max(u.y0 - 4, 14.0), 144.0)
                mb = min(max(h - u.y1 - 4, 10.0), 72.0)
            else:
                ml = mr = mt = mb = 56.7
            if w - ml - mr < 72:
                ml = mr = 36.0
            g = PageGeometry(w, h, round(ml, 2), round(mr, 2), round(mt, 2), round(mb, 2))
            for i in idxs:
                out[i] = g
        return [g for g in out if g is not None]

    def _layout_page(self, page: Page, it: _PageItems, geo: PageGeometry) -> LayoutPage:
        x0, x1 = geo.margin_left, geo.width - geo.margin_right
        gutters = find_gutters(it.flow_lines, x0, x1) if self.cfg.detect_columns else []
        bands = self._bands(it, gutters, x0, x1)

        start_y = geo.margin_top
        for band in bands:
            band_bottom = start_y
            for region in band.regions:
                region.blocks.sort(key=lambda b: b.top)
                cursor = start_y
                for blk in region.blocks:
                    blk.space_before = max(0.0, blk.top - cursor)
                    cursor += blk.space_before + (blk.bottom - blk.top)
                band_bottom = max(band_bottom, cursor)
            band.top, band.bottom = start_y, band_bottom
            start_y = band_bottom

        text_boxes = []
        for box, lines in it.boxes:
            paras, v_align = _content_in_box(lines, box)
            text_boxes.append(TextBoxBlock(bbox=box, paragraphs=paras, v_align=v_align))
        return LayoutPage(page=page, geometry=geo, bands=bands, anchored=it.anchored,
                          vector_layer=page.vector_layer, text_boxes=text_boxes)

    def _bands(self, it: _PageItems, gutters: list[tuple[float, float]], x0: float, x1: float) -> list[Band]:
        elems: list[tuple[float, Rect, str, object]] = []
        elems += [(ln.bbox.y0, ln.bbox, "line", ln) for ln in it.flow_lines]
        elems += [(t.bbox.y0, t.bbox, "table", (t, lines)) for t, lines in it.tables]
        elems += [(im.bbox.y0, im.bbox, "image", im) for im in it.inline_images]
        elems.sort(key=lambda e: e[0])
        if not gutters:
            return [self._build_band(elems, [(x0, x1)], 0.0)]

        bounds = []
        left = x0
        for g0, g1 in gutters:
            bounds.append((left, g0))
            left = g1
        bounds.append((left, x1))

        def spans_gutter(r: Rect) -> bool:
            return any(r.x0 < g0 - 1 and r.x1 > g1 + 1 for g0, g1 in gutters)

        bands: list[Band] = []
        group: list = []
        group_kind = None
        for e in elems:
            kind = "span" if spans_gutter(e[1]) else "cols"
            if group and kind != group_kind:
                bands.append(self._build_band(group, [(x0, x1)] if group_kind == "span" else bounds,
                                              gutters[0][1] - gutters[0][0]))
                group = []
            group.append(e)
            group_kind = kind
        if group:
            bands.append(self._build_band(group, [(x0, x1)] if group_kind == "span" else bounds,
                                          gutters[0][1] - gutters[0][0]))
        return bands

    def _build_band(self, elems: list, bounds: list[tuple[float, float]], gutter: float) -> Band:
        regions = [Region(a, b) for a, b in bounds]

        def region_for(r: Rect) -> Region:
            if len(regions) == 1:
                return regions[0]
            return min(regions, key=lambda rg: 0 if rg.x0 - 1 <= r.cx <= rg.x1 + 1
                       else min(abs(r.cx - rg.x0), abs(r.cx - rg.x1)))

        lines_by_region: dict[int, list[TextLine]] = {}
        for _, rect, kind, obj in elems:
            rg = region_for(rect)
            if kind == "line":
                lines_by_region.setdefault(id(rg), []).append(obj)
            elif kind == "table":
                rg.blocks.append(self._table_block(obj[0], obj[1], rg))
            else:
                rg.blocks.append(self._image_block(obj, rg))
        for rg in regions:
            rows = build_rows(lines_by_region.get(id(rg), []))
            rg.blocks.extend(build_paragraphs(rows, rg.x0, rg.x1))
        top = min((e[1].y0 for e in elems), default=0.0)
        bottom = max((e[1].y1 for e in elems), default=0.0)
        return Band(top=top, bottom=bottom, regions=regions, gutter=gutter)

    @staticmethod
    def _table_block(table: TableElement, lines: list[TextLine], region: Region) -> TableBlock:
        cells: list[CellContent] = []
        assigned: dict[int, list] = {}
        for ln in lines:
            for sp in ln.spans:
                for k, c in enumerate(table.cells):
                    if c.bbox.expand(0.5).contains_point(sp.bbox.cx, sp.bbox.cy):
                        assigned.setdefault(k, []).append((ln, sp))
                        break
        for k, c in enumerate(table.cells):
            content = CellContent(c.row, c.col, c.row_span, c.col_span, c.bbox)
            pairs = assigned.get(k, [])
            if pairs:
                by_line: dict[int, TextLine] = {}
                for ln, sp in pairs:
                    if id(ln) not in by_line:
                        by_line[id(ln)] = TextLine(spans=[], bbox=sp.bbox, angle=ln.angle,
                                                   vertical=ln.vertical)
                    tl = by_line[id(ln)]
                    tl.spans.append(sp)
                    tl.bbox = tl.bbox.union(sp.bbox)
                content.paragraphs, content.v_align = _content_in_box(list(by_line.values()), c.bbox)
            cells.append(content)
        return TableBlock(table=table, cells=cells, left=table.bbox.x0 - region.x0)

    @staticmethod
    def _image_block(im: ImageElement, region: Region) -> ImageBlock:
        w = region.width
        if abs(im.bbox.cx - (region.x0 + region.x1) / 2) <= max(4.0, 0.02 * w) and im.bbox.x0 - region.x0 > 10:
            return ImageBlock(im, Align.CENTER, 0.0)
        if abs(im.bbox.x1 - region.x1) <= 4 and im.bbox.x0 - region.x0 > 0.3 * w:
            return ImageBlock(im, Align.RIGHT, 0.0)
        return ImageBlock(im, Align.LEFT, im.bbox.x0 - region.x0)
