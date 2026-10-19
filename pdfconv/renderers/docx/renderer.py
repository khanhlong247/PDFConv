from __future__ import annotations

from collections import Counter

from docx import Document as new_docx
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT as VA
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH as AL
from docx.enum.text import WD_BREAK, WD_LINE_SPACING
from docx.enum.text import WD_TAB_ALIGNMENT as TA
from docx.enum.text import WD_TAB_LEADER as TL
from docx.shared import Pt, RGBColor

from ...domain.layout import (Align, Band, CellContent, ImageBlock, LayoutDocument, LayoutPage,
                              PageGeometry, ParagraphBlock, ParagraphKind, Region, Run, SegmentKind,
                              TableBlock)
from ...domain.models import ImageRole
from ...domain.text import strip_xml_invalid
from ..base import DocumentRenderer, OutputFormat, RenderContext, RenderOutput
from .ooxml import (floating_image, floating_textbox, no_widow_control, set_columns, set_font_name,
                    table_setup)

CELL_MARGIN = 2.0
SLACK = 6.0
_ALIGN = {Align.LEFT: AL.LEFT, Align.CENTER: AL.CENTER, Align.RIGHT: AL.RIGHT, Align.JUSTIFY: AL.JUSTIFY}
_LEADER = {".": TL.DOTS, "_": TL.LINES, "-": TL.DASHES, "·": TL.MIDDLE_DOT}


class DocxRenderer(DocumentRenderer):
    format = OutputFormat.DOCX

    def render(self, layout: LayoutDocument, ctx: RenderContext) -> RenderOutput:
        self.ctx = ctx
        self.z = 10
        self.shape_id = 100_000
        d = new_docx()
        self._setup_styles(d, layout)
        prev_geo: PageGeometry | None = None
        for i, lp in enumerate(layout.pages):
            g = lp.geometry
            if i == 0:
                self._apply_geometry(d.sections[0], g)
                page_break = False
            elif not self._same_geo(g, prev_geo):
                self._apply_geometry(d.add_section(WD_SECTION.NEW_PAGE), g)
                page_break = False
            else:
                page_break = True
            prev_geo = g
            anchor_par = self._anchor_paragraph(d, page_break)
            self._page_graphics(anchor_par, lp)
            self._text_boxes(d, anchor_par, lp)
            for k, band in enumerate(lp.bands):
                self._band(d, band, lp, first=(k == 0))
        d.core_properties.title = layout.document.metadata.get("title", ctx.stem)[:250]
        d.core_properties.author = layout.document.metadata.get("author", "")[:250]
        d.core_properties.comments = "Chuyển đổi bởi pdfconv"
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        out = ctx.output_dir / f"{ctx.stem}.docx"
        d.save(out)
        return RenderOutput(main_file=out, files=[out])

    @staticmethod
    def _setup_styles(d, layout: LayoutDocument) -> None:
        fams = Counter()
        sizes = Counter()
        for p in layout.document.pages:
            for ln in p.lines:
                for s in ln.spans:
                    fams[s.font.family] += len(s.text)
                    sizes[round(s.size * 2) / 2] += len(s.text)
        st = d.styles["Normal"]
        family = fams.most_common(1)[0][0] if fams else "Times New Roman"
        st.font.name = family
        set_font_name(st.element, family)
        st.font.size = Pt(sizes.most_common(1)[0][0] if sizes else 12)
        pf = st.paragraph_format
        pf.space_before = pf.space_after = Pt(0)
        pf.line_spacing = 1.0

    @staticmethod
    def _same_geo(a: PageGeometry, b: PageGeometry | None) -> bool:
        return b is not None and (round(a.width), round(a.height)) == (round(b.width), round(b.height))

    @staticmethod
    def _apply_geometry(section, g: PageGeometry) -> None:
        section.orientation = WD_ORIENT.LANDSCAPE if g.width > g.height else WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Pt(g.width), Pt(g.height)
        section.left_margin, section.right_margin = Pt(g.margin_left), Pt(g.margin_right)
        section.top_margin, section.bottom_margin = Pt(g.margin_top), Pt(max(4.0, g.margin_bottom * 0.35))
        section.header_distance = Pt(min(12, g.margin_top / 2))
        section.footer_distance = Pt(min(12, g.margin_bottom / 2))

    @staticmethod
    def _anchor_paragraph(d, page_break: bool):
        p = d.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(1)
        pf.page_break_before = page_break
        return p

    def _page_graphics(self, p, lp: LayoutPage) -> None:
        items = []
        if lp.vector_layer is not None:
            items.append((lp.vector_layer, True))
        for im in sorted(lp.anchored, key=lambda im: im.z):
            behind = im.role in (ImageRole.BACKGROUND, ImageRole.PAGE_SCAN, ImageRole.VECTOR_LAYER)
            items.append((im, behind))

        items.sort(key=lambda t: (not t[1], t[0].z))
        for im, behind in items:
            b = im.bbox
            self.z += 1
            floating_image(p, str(self.ctx.asset_root / im.file), b.x0, b.y0, b.width, b.height,
                           behind=behind, z=self.z)

    def _text_boxes(self, d, anchor_par, lp: LayoutPage) -> None:
        for tb in lp.text_boxes:
            elems = []
            inner_w = tb.bbox.width - 2 * CELL_MARGIN
            for blk in tb.paragraphs:
                p = d.add_paragraph()
                self._fill_box_paragraph(p, blk, tb.bbox.x0, inner_w)
                p._p.getparent().remove(p._p)
                elems.append(p._p)
            self.z += 1
            self.shape_id += 1
            floating_textbox(anchor_par, elems, tb.bbox.x0 + CELL_MARGIN, tb.bbox.y0,
                             inner_w, tb.bbox.height, tb.v_align, self.z, self.shape_id)

    def _band(self, d, band: Band, lp: LayoutPage, first: bool) -> None:
        if band.columns == 1:
            self._region(d, band.regions[0], first)
            return
        sec = d.add_section(WD_SECTION.CONTINUOUS)
        self._apply_geometry(sec, lp.geometry)
        set_columns(sec, band.columns, band.gutter)
        for k, rg in enumerate(band.regions):
            last_par = self._region(d, rg, False)
            if k < len(band.regions) - 1 and last_par is not None:
                last_par.add_run().add_break(WD_BREAK.COLUMN)
        sec = d.add_section(WD_SECTION.CONTINUOUS)
        self._apply_geometry(sec, lp.geometry)
        set_columns(sec, 1, 0)

    def _region(self, d, rg: Region, first: bool):
        last = None
        for k, blk in enumerate(rg.blocks):
            sb = blk.space_before - (1.0 if (first and k == 0) else 0.0)
            if isinstance(blk, ParagraphBlock):
                last = self._paragraph(d, blk, rg.x0, rg.width, max(0.0, sb))
            elif isinstance(blk, TableBlock):
                self._spacer(d, max(sb, 1.0))
                self._table(d, blk)
                last = None
            elif isinstance(blk, ImageBlock):
                last = self._image(d, blk, max(0.0, sb))
        return last

    def _add_runs(self, p, runs: list[Run]) -> None:
        for r in runs:
            text = strip_xml_invalid(r.text)
            if not text:
                continue
            run = p.add_run(text)
            run.font.name = r.font.family
            set_font_name(run._r, r.font.family)
            run.font.size = Pt(round(r.size * 2) / 2 if r.size >= 2 else 1)
            run.bold = r.font.bold
            run.italic = r.font.italic
            if not r.color.is_black:
                run.font.color.rgb = RGBColor(*r.color.rgb255)
            if r.superscript:
                run.font.superscript = True

    @staticmethod
    def _base_format(p, line_height: float, space_before: float) -> None:
        pf = p.paragraph_format
        pf.space_before = Pt(round(space_before, 1))
        pf.space_after = Pt(0)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(round(line_height, 1))
        no_widow_control(p)

    def _paragraph(self, container, blk: ParagraphBlock, x0: float, width: float, sb: float):
        p = container.add_paragraph()
        self._base_format(p, blk.line_height, sb)
        pf = p.paragraph_format
        if blk.kind is ParagraphKind.TABBED:
            self._tabbed(p, blk, x0, width)
            return p
        pf.alignment = _ALIGN[blk.align]
        if blk.align in (Align.LEFT, Align.JUSTIFY):
            pf.left_indent = Pt(blk.left)
            pf.first_line_indent = Pt(blk.first_indent)
            pf.right_indent = Pt(-SLACK)
        elif blk.align is Align.CENTER:
            pf.left_indent = Pt(-SLACK + max(0.0, 2 * blk.shift))
            pf.right_indent = Pt(-SLACK + max(0.0, -2 * blk.shift))
        else:
            pf.left_indent = Pt(-SLACK)
            pf.right_indent = Pt(-blk.shift)
        self._add_runs(p, blk.runs())
        return p

    def _tabbed(self, p, blk: ParagraphBlock, x0: float, width: float) -> None:
        segs = blk.rows[0].segments
        stops: list[tuple[float, object, object]] = []
        cur = 0.0
        last_text = max((i for i, s in enumerate(segs) if s.kind is SegmentKind.TEXT), default=-1)
        for i, seg in enumerate(segs):
            sx0, sx1 = seg.x0 - x0, seg.x1 - x0
            if seg.kind is SegmentKind.LEADER:
                if sx0 - cur > 3:
                    p.add_run("\t")
                    stops.append((sx0, TA.LEFT, TL.SPACES))
                p.add_run("\t")
                stops.append((sx1, TA.LEFT, _LEADER.get(seg.leader_char, TL.DOTS)))
                cur = sx1
                continue
            right_aligned = (i == last_text and i == len(segs) - 1 and abs(sx1 - width) <= 3
                             and sx0 - cur > 20)
            if right_aligned:
                p.add_run("\t")
                stops.append((sx1, TA.RIGHT, TL.SPACES))
            elif sx0 - cur > 1.5 or (i == 0 and sx0 > 1.5):
                p.add_run("\t")
                stops.append((sx0, TA.LEFT, TL.SPACES))
            self._add_runs(p, seg.runs)
            cur = sx1
        pf = p.paragraph_format
        added: list[float] = []
        for pos, align, leader in sorted(stops, key=lambda s: s[0]):
            if added and abs(pos - added[-1]) < 0.8:
                continue
            pf.tab_stops.add_tab_stop(Pt(max(pos, 0.5)), align, leader)
            added.append(pos)
        overflow = max(added, default=0) - width
        pf.right_indent = Pt(-(max(overflow, 0) + SLACK))

    def _spacer(self, container, height: float) -> None:
        p = container.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(round(max(height, 1.0), 1))
        r = p.add_run()
        r.font.size = Pt(1)

    def _table(self, d, tb: TableBlock) -> None:
        t = tb.table
        widths = [t.col_edges[i + 1] - t.col_edges[i] for i in range(t.n_cols)]
        heights = [t.row_edges[i + 1] - t.row_edges[i] for i in range(t.n_rows)]
        table = d.add_table(rows=t.n_rows, cols=t.n_cols)
        table.autofit = False
        table_setup(table, widths, tb.left + CELL_MARGIN, CELL_MARGIN)
        need = [0.0] * t.n_rows
        for c in tb.cells:
            if c.row_span == 1 and c.row < t.n_rows:
                h = sum(p.space_before + p.line_height * len(p.rows) for p in c.paragraphs)
                need[c.row] = max(need[c.row], h)
        for r, row in enumerate(table.rows):
            row.height = Pt(heights[r])
            row.height_rule = (WD_ROW_HEIGHT_RULE.EXACTLY if need[r] <= heights[r] - 1
                               else WD_ROW_HEIGHT_RULE.AT_LEAST)
        for c in tb.cells:
            r1 = min(c.row + c.row_span - 1, t.n_rows - 1)
            c1 = min(c.col + c.col_span - 1, t.n_cols - 1)
            cell = table.cell(c.row, c.col)
            if (r1, c1) != (c.row, c.col):
                try:
                    cell = cell.merge(table.cell(r1, c1))
                except Exception:
                    pass
            self._cell(cell, c, sum(widths[c.col:c1 + 1]) - 2 * CELL_MARGIN)

    def _cell(self, cell, c: CellContent, inner_w: float) -> None:
        cell.vertical_alignment = {"center": VA.CENTER, "bottom": VA.BOTTOM}.get(c.v_align, VA.TOP)
        first = True
        for blk in c.paragraphs:
            if first and len(cell.paragraphs) == 1 and not cell.paragraphs[0].text:
                p = cell.paragraphs[0]
            else:
                p = cell.add_paragraph()
            first = False
            self._fill_box_paragraph(p, blk, c.bbox.x0, inner_w)

    def _fill_box_paragraph(self, p, blk: ParagraphBlock, box_x0: float, inner_w: float) -> None:
        self._base_format(p, blk.line_height, blk.space_before)
        if blk.kind is ParagraphKind.TABBED:
            for k, seg in enumerate(blk.rows[0].segments):
                if k:
                    p.add_run(" ")
                self._add_runs(p, seg.runs)
            return
        p.paragraph_format.alignment = _ALIGN[blk.align if blk.align is not Align.JUSTIFY else Align.LEFT]
        if blk.align is Align.LEFT:
            p.paragraph_format.left_indent = Pt(max(0.0, min(blk.left, inner_w - 10)))
        self._add_runs(p, blk.runs())

    def _image(self, d, ib: ImageBlock, sb: float):
        p = d.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = Pt(round(sb, 1))
        pf.line_spacing = 1.0
        pf.alignment = _ALIGN[ib.align]
        if ib.align is Align.LEFT:
            pf.left_indent = Pt(ib.left)
        b = ib.image.bbox
        p.add_run().add_picture(str(self.ctx.asset_root / ib.image.file), width=Pt(b.width),
                                height=Pt(b.height))
        return p
