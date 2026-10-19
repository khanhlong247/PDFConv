from __future__ import annotations

from ... import __version__
from ...domain.layout import (Align, Band, CellContent, ImageBlock, LayoutDocument, LayoutPage,
                              ParagraphBlock, ParagraphKind, Region, Run, SegmentKind, TableBlock)
from ...domain.models import ImageElement, ImageRole
from ..base import DocumentRenderer, OutputFormat, RenderContext, RenderOutput
from .common import (FIT_MACRO, ColorRegistry, FontRegistry, StyleRegistry, copy_assets, escape,
                     num)

TABCOLSEP = 2.0


class LatexFlowRenderer(DocumentRenderer):
    format = OutputFormat.LATEX

    def render(self, layout: LayoutDocument, ctx: RenderContext) -> RenderOutput:
        self.colors = ColorRegistry()
        self.fonts = FontRegistry()
        self.styles = StyleRegistry(self.fonts, self.colors)
        self.used: set[str] = set()
        warnings: list[str] = []

        first = layout.pages[0].geometry
        body: list[str] = []
        for i, lp in enumerate(layout.pages):
            g = lp.geometry
            if (round(g.width), round(g.height)) != (round(first.width), round(first.height)):
                warnings.append(f"Trang {i + 1} khác khổ giấy; chế độ flow dùng khổ của trang đầu.")
            if i:
                body.append(r"\clearpage")
            body.append(f"% ================= trang {i + 1}")
            bg = self._background(lp)
            if bg:
                body.append(bg)
            for k, band in enumerate(lp.bands):
                body.append(self._band(band, first_on_page=(k == 0)))
            if not any(rg.blocks for band in lp.bands for rg in band.regions):
                body.append(r"\null")

        doc = layout.document
        content = "\n".join(body)
        tex = "\n".join([
            "% !TEX program = xelatex",
            f"% Sinh tự động bởi pdfconv {__version__} từ '{doc.name}' – chế độ flow (dễ chỉnh sửa)",
            r"\documentclass{article}",
            rf"\usepackage[paperwidth={num(first.width)}bp,paperheight={num(first.height)}bp,"
            rf"left={num(first.margin_left)}bp,right={num(first.margin_right)}bp,"
            rf"top={num(first.margin_top)}bp,bottom={num(max(4.0, first.margin_bottom * 0.35))}bp,"
            r"headheight=0pt,headsep=0pt,footskip=0pt]{geometry}",
            r"\usepackage{fontspec}",
            r"\usepackage{xcolor}",
            r"\usepackage{graphicx}",
            r"\usepackage{eso-pic}",
            r"\usepackage{array}",
            r"\usepackage{multicol}",
            r"\pagestyle{empty}",
            r"\setlength{\parindent}{0pt}",
            r"\setlength{\parskip}{0pt}",
            r"\setlength{\topskip}{0pt}",
            r"\setlength{\lineskip}{0pt}",
            r"\setlength{\lineskiplimit}{0pt}",
            r"\raggedbottom",
            rf"\setlength{{\tabcolsep}}{{{num(TABCOLSEP)}bp}}",
            r"\setlength{\arrayrulewidth}{0.5bp}",
            r"\renewcommand{\arraystretch}{0.5}",
            r"\emergencystretch=3em",
            self.colors.preamble(),
            self.fonts.preamble(),
            self.styles.preamble(),
            FIT_MACRO,
            r"% \pdcLead{rộng}{ký tự}: dòng chấm để điền thông tin; \pdcRule{rộng}: dòng gạch dưới",
            r"\newcommand\pdcLead[2]{\hbox to #1{\leaders\hbox to .32em{\hss#2\hss}\hfill}}",
            r"\newcommand\pdcRule[1]{\hbox to #1{\leaders\hrule height .35bp depth .35bp\hfill}}",
            r"\begin{document}",
            content,
            r"\end{document}",
            "",
        ])
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        main = ctx.output_dir / f"{ctx.stem}.tex"
        main.write_text(tex, encoding="utf-8")
        files = [main] + copy_assets(self.used, ctx.asset_root, ctx.output_dir)
        return RenderOutput(main_file=main, files=files, warnings=warnings)

    def _background(self, lp: LayoutPage) -> str:
        H = lp.geometry.height
        imgs: list[ImageElement] = []
        if lp.vector_layer is not None:
            imgs.append(lp.vector_layer)
        imgs += sorted(lp.anchored, key=lambda im: (im.role not in (ImageRole.BACKGROUND,
                                                                    ImageRole.PAGE_SCAN), im.z))
        puts = []
        for im in imgs:
            self.used.add(im.file)
            b = im.bbox
            puts.append(rf"\put({num(b.x0)},{num(H - b.y1)}){{\includegraphics"
                        rf"[width={num(b.width)}bp,height={num(b.height)}bp]{{{im.file}}}}}")
        for tb in lp.text_boxes:
            b = tb.bbox
            inner_w = max(b.width - 2 * TABCOLSEP, 1)
            pos = {"center": "c", "bottom": "b"}.get(tb.v_align, "t")
            puts.append(rf"\put({num(b.x0 + TABCOLSEP)},{num(H - b.y1)}){{\parbox[b][{num(b.height)}bp][{pos}]"
                        rf"{{{num(inner_w)}bp}}{{{self._box_paragraphs(tb.paragraphs, inner_w)}}}}}")
        if not puts:
            return ""
        return (r"\AddToShipoutPictureBG*{\setlength{\unitlength}{1bp}\AtPageLowerLeft{%" + "\n"
                + "\n".join(puts) + "}}")

    def _band(self, band: Band, first_on_page: bool) -> str:
        if band.columns == 1:
            return "\n".join(self._region(band.regions[0], first_on_page))
        out = [rf"\setlength{{\columnsep}}{{{num(band.gutter)}bp}}",
               rf"\begin{{multicols}}{{{band.columns}}}"]
        for k, rg in enumerate(band.regions):
            if k:
                out.append(r"\columnbreak")
            out.extend(self._region(rg, False))
        out.append(r"\end{multicols}")
        return "\n".join(out)

    def _region(self, rg: Region, first_on_page: bool) -> list[str]:
        out: list[str] = []
        prev_lh: float | None = None
        for k, blk in enumerate(rg.blocks):
            is_par = isinstance(blk, ParagraphBlock)
            v = blk.space_before
            if is_par and k > 0:
                v += 0.2 * ((prev_lh or 0.0) - blk.line_height)
            if k == 0 and first_on_page:
                out.append(rf"\vspace*{{{num(max(v, 0.0))}bp}}\nointerlineskip")
            elif abs(v) > 0.3:
                out.append(rf"\vspace{{{num(v)}bp}}")
            prev_lh = blk.line_height if is_par else None
            if isinstance(blk, ParagraphBlock):
                out.append(self._paragraph(blk, rg.x0))
            elif isinstance(blk, TableBlock):
                out.append(self._table(blk))
            elif isinstance(blk, ImageBlock):
                out.append(self._image_block(blk))
        return out

    def _runs(self, runs: list[Run]) -> str:
        parts = []
        for r in runs:
            st = self.styles.macro(r.font, r.size, r.color)
            text = escape(r.text, keep_spaces=True)
            if r.superscript:
                text = rf"\raisebox{{0.35em}}{{{text}}}"
            parts.append(f"{{{st} {text}}}")
        return "".join(parts)

    @staticmethod
    def _strut(lh: float) -> str:
        return rf"\rule[{num(-0.2 * lh)}bp]{{0pt}}{{{num(lh)}bp}}"

    def _paragraph(self, p: ParagraphBlock, region_x0: float) -> str:
        lh = num(p.line_height)
        strut = self._strut(p.line_height)
        if p.kind is ParagraphKind.TABBED:
            return (rf"{{\setlength{{\baselineskip}}{{{lh}bp}}\noindent\makebox[\linewidth][l]{{{strut}"
                    + self._tabbed_row(p, region_x0) + r"}\par}")
        align = {Align.CENTER: r"\centering", Align.RIGHT: r"\raggedleft",
                 Align.LEFT: r"\raggedright", Align.JUSTIFY: ""}[p.align]
        skips = ""
        if p.align in (Align.LEFT, Align.JUSTIFY) and abs(p.left) > 0.3:
            skips = rf"\leftskip={num(p.left)}bp" + (" plus 0pt" if p.align is Align.LEFT else "")
        elif p.align is Align.CENTER and abs(p.shift) > 0.3:
            side = r"\leftskip" if p.shift > 0 else r"\rightskip"
            skips = rf"{side}={num(2 * abs(p.shift))}bp plus 1fil"
        elif p.align is Align.RIGHT and abs(p.shift) > 0.3:
            skips = rf"\rightskip={num(max(0.0, -p.shift))}bp"
        indent = rf"\hspace*{{{num(p.first_indent)}bp}}" if abs(p.first_indent) > 0.5 else ""
        return (rf"{{\setlength{{\baselineskip}}{{{lh}bp}}{align}{skips}\noindent{strut}{indent}"
                + self._runs(p.runs()) + r"\par}")

    def _leader(self, seg, width: float) -> str:
        r0 = seg.runs[0]
        st = self.styles.macro(r0.font, r0.size, r0.color)
        if seg.leader_char == "_":
            return rf"{{{st}\pdcRule{{{num(width)}bp}}}}"
        ch = "-" if seg.leader_char == "-" else "."
        return rf"{{{st}\pdcLead{{{num(width)}bp}}{{{ch}}}}}"

    def _tabbed_row(self, p: ParagraphBlock, region_x0: float) -> str:
        parts = []
        for seg in p.rows[0].segments:
            x = num(seg.x0 - region_x0)
            if seg.kind is SegmentKind.LEADER:
                parts.append(rf"\rlap{{\hspace*{{{x}bp}}{self._leader(seg, seg.width)}}}")
            else:
                parts.append(rf"\rlap{{\hspace*{{{x}bp}}\pdcFit{{{num(seg.width + 1.0)}bp}}"
                             rf"{{{self._runs(seg.runs)}}}}}")
        return "".join(parts)

    def _table(self, tb: TableBlock) -> str:
        t = tb.table
        widths = [t.col_edges[i + 1] - t.col_edges[i] for i in range(t.n_cols)]
        heights = [t.row_edges[i + 1] - t.row_edges[i] for i in range(t.n_rows)]
        grid: dict[tuple[int, int], CellContent] = {}
        for c in tb.cells:
            for r in range(c.row, c.row + c.row_span):
                for k in range(c.col, c.col + c.col_span):
                    grid[(r, k)] = c

        def inner(w: float) -> str:
            return num(max(w - 2 * TABCOLSEP - 0.5, 1))

        def continues_down(r: int, k: int) -> bool:
            c = grid.get((r, k))
            return c is not None and c.row + c.row_span - 1 > r

        spec = "|" + "|".join(f"p{{{inner(w)}bp}}" for w in widths) + "|"
        lines = [rf"\noindent\hspace*{{{num(tb.left)}bp}}\begin{{tabular}}[b]{{{spec}}}", r"\hline"]
        for r in range(t.n_rows):
            cells_tex = []
            k = 0
            h = max(heights[r] - 0.5, 1)
            strut = rf"\rule[{num(-0.3 * h)}bp]{{0pt}}{{{num(h)}bp}}"
            while k < t.n_cols:
                c = grid.get((r, k))
                lead = strut if k == 0 else ""
                if c is None:
                    cells_tex.append(rf"\multicolumn{{1}}{{{'|' if k == 0 else ''}p{{{inner(widths[k])}bp}}|}}"
                                     rf"{{{lead}}}")
                    k += 1
                    continue
                span = min(c.col_span, t.n_cols - k)
                w = sum(widths[k:k + span])
                content = self._cell(c, w) if c.row == r else ""
                cells_tex.append(rf"\multicolumn{{{span}}}{{{'|' if k == 0 else ''}p{{{inner(w)}bp}}|}}"
                                 rf"{{{lead}{content}}}")
                k += span
            lines.append(" & ".join(cells_tex) + r"\\")
            if r == t.n_rows - 1 or not any(continues_down(r, k) for k in range(t.n_cols)):
                lines.append(r"\hline")
            else:
                segs, k = [], 0
                while k < t.n_cols:
                    if continues_down(r, k):
                        k += 1
                        continue
                    start = k
                    while k < t.n_cols and not continues_down(r, k):
                        k += 1
                    segs.append(rf"\cline{{{start + 1}-{k}}}")
                lines.append("".join(segs))
        lines.append(r"\end{tabular}\par")
        return "\n".join(lines)

    def _cell(self, c: CellContent, width: float) -> str:
        inner_w = max(width - 2 * TABCOLSEP - 0.5, 1)
        body = self._box_paragraphs(c.paragraphs, inner_w)
        if not body:
            return ""
        pos = {"center": "c", "bottom": "b"}.get(c.v_align, "t")
        return rf"\parbox[{pos}]{{{num(inner_w)}bp}}{{{body}}}"

    def _box_paragraphs(self, paragraphs: list[ParagraphBlock], inner_w: float) -> str:
        paras = []
        for p in paragraphs:
            if p.kind is ParagraphKind.TABBED:
                text = r"\ ".join(self._runs(s.runs) for s in p.rows[0].segments)
                align = r"\raggedright"
            else:
                text = self._runs(p.runs())
                align = {Align.CENTER: r"\centering", Align.RIGHT: r"\raggedleft"}.get(p.align, r"\raggedright")
            paras.append(rf"{{\setlength{{\baselineskip}}{{{num(p.line_height)}bp}}{align} {text}\par}}")
        return "".join(paras)

    def _image_block(self, ib: ImageBlock) -> str:
        self.used.add(ib.image.file)
        b = ib.image.bbox
        img = rf"\includegraphics[width={num(b.width)}bp,height={num(b.height)}bp]{{{ib.image.file}}}"
        if ib.align is Align.CENTER:
            return rf"{{\centering {img}\par}}"
        if ib.align is Align.RIGHT:
            return rf"{{\raggedleft {img}\par}}"
        return rf"\noindent\hspace*{{{num(ib.left)}bp}}{img}\par"
