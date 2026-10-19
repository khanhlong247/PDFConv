from __future__ import annotations

from ... import __version__
from ...domain.layout import LayoutDocument
from ...domain.models import ImageElement, ImageRole, Page, Shape, TextLine, TextSpan
from ..base import DocumentRenderer, OutputFormat, RenderContext, RenderOutput
from .common import (FIT_MACRO, ColorRegistry, FontRegistry, StyleRegistry, copy_assets, escape,
                     num)

_CAP = {0: "butt", 1: "round", 2: "rect"}
_JOIN = {0: "miter", 1: "round", 2: "bevel"}


class LatexExactRenderer(DocumentRenderer):
    format = OutputFormat.LATEX

    def render(self, layout: LayoutDocument, ctx: RenderContext) -> RenderOutput:
        doc = layout.document
        colors = ColorRegistry()
        fonts = FontRegistry()
        styles = StyleRegistry(fonts, colors)
        used_images: set[str] = set()
        pages_tex: list[str] = []
        for page in doc.pages:
            pages_tex.append(self._page(page, styles, colors, used_images))

        first = doc.pages[0]
        body = "\n".join(pages_tex)
        tex = "\n".join([
            "% !TEX program = xelatex",
            f"% Sinh tự động bởi pdfconv {__version__} từ '{doc.name}' – chế độ exact (định vị tuyệt đối)",
            r"\documentclass{article}",
            rf"\usepackage[paperwidth={num(first.width)}bp,paperheight={num(first.height)}bp,margin=0pt]{{geometry}}",
            r"\usepackage{fontspec}",
            r"\usepackage{xcolor}",
            r"\usepackage{graphicx}",
            r"\usepackage{eso-pic}",
            r"\usepackage{tikz}",
            r"\pagestyle{empty}",
            r"\setlength{\parindent}{0pt}",
            r"\graphicspath{{./}}",
            colors.preamble(),
            fonts.preamble(),
            styles.preamble(),
            FIT_MACRO,
            r"% \pdcPage{rộng}{cao}{nội dung}: một trang PDF, toạ độ bp tính từ góc dưới-trái",
            r"\newcommand\pdcPage[3]{\clearpage\setlength{\paperwidth}{#1bp}\setlength{\paperheight}{#2bp}%",
            r"  \setlength{\pdfpagewidth}{\paperwidth}\setlength{\pdfpageheight}{\paperheight}%",
            r"  \AddToShipoutPictureFG*{\setlength{\unitlength}{1bp}\AtPageLowerLeft{#3}}\null}",
            r"\newcommand\pdcT[4]{\put(#1,#2){\pdcFit{#3bp}{#4}}}",
            r"\newcommand\pdcI[5]{\put(#1,#2){\includegraphics[width=#3bp,height=#4bp]{#5}}}",
            r"\begin{document}",
            body,
            r"\end{document}",
            "",
        ])
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        main = ctx.output_dir / f"{ctx.stem}.tex"
        main.write_text(tex, encoding="utf-8")
        files = [main] + copy_assets(used_images, ctx.asset_root, ctx.output_dir)
        return RenderOutput(main_file=main, files=files)

    def _page(self, page: Page, styles: StyleRegistry, colors: ColorRegistry, used: set[str]) -> str:
        H = page.height
        out: list[str] = [f"% ---------------- trang {page.index + 1}",
                          rf"\pdcPage{{{num(page.width)}}}{{{num(H)}}}{{%"]
        items: list[tuple[int, str, object]] = []
        if page.complex_graphics and (page.vector_layer_full or page.vector_layer):
            items.append((-1, "image", page.vector_layer_full or page.vector_layer))
        items += [(s.z, "shape", s) for s in page.shapes]
        items += [(im.z, "image", im) for im in page.images if im.role is not ImageRole.VECTOR_LAYER]
        items.sort(key=lambda t: t[0])

        shape_buf: list[Shape] = []
        for _, kind, obj in items:
            if kind == "shape":
                shape_buf.append(obj)
                continue
            if shape_buf:
                out.append(self._tikz(shape_buf, H, colors))
                shape_buf = []
            out.append(self._image(obj, H, used))
        if shape_buf:
            out.append(self._tikz(shape_buf, H, colors))

        for line in page.lines:
            out.extend(self._line(line, H, styles))
        out.append("}")
        return "\n".join(out)

    @staticmethod
    def _image(im: ImageElement, H: float, used: set[str]) -> str:
        used.add(im.file)
        b = im.bbox
        return rf"\pdcI{{{num(b.x0)}}}{{{num(H - b.y1)}}}{{{num(b.width)}}}{{{num(b.height)}}}{{{im.file}}}"

    def _line(self, line: TextLine, H: float, styles: StyleRegistry) -> list[str]:
        out = []
        for span in line.spans:
            st = styles.macro(span.font, span.size, span.color)
            if not line.is_horizontal:
                text = escape(span.text.strip())
                if text:
                    out.append(rf"\put({num(span.origin.x)},{num(H - span.origin.y)})"
                               rf"{{\rotatebox{{{num(line.angle if not line.vertical else -90)}}}{{{st} {text}}}}}")
                continue
            for x0, x1, text in self._pieces(span):
                out.append(rf"\pdcT{{{num(x0)}}}{{{num(H - span.origin.y)}}}{{{num(x1 - x0 + 0.6)}}}"
                           rf"{{{st} {escape(text)}}}")
        return out

    @staticmethod
    def _pieces(span: TextSpan) -> list[tuple[float, float, str]]:
        pieces: list[tuple[float, float, str]] = []
        cur: list = []
        last_x1 = None

        def flush():
            if cur:
                pieces.append((cur[0].x0, cur[-1].x1, "".join(g.char for g in cur)))
            cur.clear()

        for g in span.glyphs:
            if g.char == " ":
                flush()
                continue
            if cur and last_x1 is not None and g.x0 - last_x1 > 0.3 * span.size:
                flush()
            cur.append(g)
            last_x1 = g.x1
        flush()
        return pieces

    @staticmethod
    def _tikz(shapes: list[Shape], H: float, colors: ColorRegistry) -> str:
        lines = [r"\put(0,0){\begin{tikzpicture}[x=1bp,y=1bp,overlay]"]
        for s in shapes:
            path = LatexExactRenderer._path(s, H)
            if not path:
                continue
            opts = []
            if s.fill is not None:
                opts.append(f"fill={colors.name(s.fill)}")
                if s.fill_opacity < 1:
                    opts.append(f"fill opacity={num(s.fill_opacity)}")
                if s.even_odd:
                    opts.append("even odd rule")
            if s.stroke is not None:
                opts.append(f"draw={colors.name(s.stroke)}")
                opts.append(f"line width={num(max(s.width, 0.25))}bp")
                if s.stroke_opacity < 1:
                    opts.append(f"draw opacity={num(s.stroke_opacity)}")
                if s.dashes:
                    pat = " ".join(f"{'on' if i % 2 == 0 else 'off'} {num(max(v, 0.01))}bp"
                                   for i, v in enumerate(s.dashes if len(s.dashes) % 2 == 0
                                                         else s.dashes * 2))
                    opts.append(f"dash pattern={pat}")
                    if s.dash_phase:
                        opts.append(f"dash phase={num(s.dash_phase)}bp")
                if s.line_cap:
                    opts.append(f"line cap={_CAP.get(s.line_cap, 'butt')}")
                if s.line_join:
                    opts.append(f"line join={_JOIN.get(s.line_join, 'miter')}")
            lines.append(rf"\path[{','.join(opts)}] {path};")
        lines.append(r"\end{tikzpicture}}")
        return "\n".join(lines)

    @staticmethod
    def _path(s: Shape, H: float) -> str:
        def p(pt) -> str:
            return f"({num(pt.x)},{num(H - pt.y)})"

        parts: list[str] = []
        cur = None
        for seg in s.segments:
            pts = seg.points
            if seg.op == "re":
                parts.append(f"{p(pts[0])} rectangle {p(pts[1])}")
                cur = None
            elif seg.op == "qu":
                parts.append(f"{p(pts[0])} -- {p(pts[1])} -- {p(pts[2])} -- {p(pts[3])} -- cycle")
                cur = None
            elif seg.op == "l":
                if cur is None or abs(cur.x - pts[0].x) > 0.01 or abs(cur.y - pts[0].y) > 0.01:
                    parts.append(p(pts[0]))
                parts.append(f"-- {p(pts[1])}")
                cur = pts[1]
            elif seg.op == "c":
                if cur is None or abs(cur.x - pts[0].x) > 0.01 or abs(cur.y - pts[0].y) > 0.01:
                    parts.append(p(pts[0]))
                parts.append(f".. controls {p(pts[1])} and {p(pts[2])} .. {p(pts[3])}")
                cur = pts[3]
        if s.close_path and cur is not None:
            parts.append("-- cycle")
        return " ".join(parts)
