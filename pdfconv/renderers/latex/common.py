from __future__ import annotations

import re
import shutil
from pathlib import Path

from ...domain.models import Color, FontInfo, GenericFamily
from ...domain.text import strip_xml_invalid

_ESCAPE = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#",
    "^": r"\textasciicircum{}", "_": r"\_", "%": r"\%", "~": r"\textasciitilde{}",
    " ": "~", "\n": " ", "\r": " ",
}


def escape(text: str, keep_spaces: bool = False) -> str:
    out = "".join(_ESCAPE.get(c, c) for c in strip_xml_invalid(text))
    if keep_spaces:
        out = re.sub(r" {2,}", lambda m: " " + r"\ " * (len(m.group()) - 1), out)
    return out


def num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def alpha_id(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s


FALLBACKS = {
    GenericFamily.SERIF: ["Times New Roman", "Liberation Serif", "TeX Gyre Termes", "DejaVu Serif",
                          "Noto Serif"],
    GenericFamily.SANS: ["Arial", "Liberation Sans", "TeX Gyre Heros", "DejaVu Sans", "Noto Sans"],
    GenericFamily.MONO: ["Courier New", "Liberation Mono", "TeX Gyre Cursor", "DejaVu Sans Mono"],
    GenericFamily.SYMBOL: ["DejaVu Sans", "Segoe UI Symbol", "Noto Sans Symbols", "Liberation Sans"],
}

FILE_FALLBACK = {
    GenericFamily.SERIF: ("lmroman10-regular.otf", "lmroman10-bold.otf", "lmroman10-italic.otf",
                          "lmroman10-bolditalic.otf"),
    GenericFamily.SANS: ("lmsans10-regular.otf", "lmsans10-bold.otf", "lmsans10-oblique.otf",
                         "lmsans10-boldoblique.otf"),
    GenericFamily.MONO: ("lmmono10-regular.otf", "lmmonolt10-bold.otf", "lmmono10-italic.otf",
                         "lmmonolt10-boldoblique.otf"),
}
FILE_FALLBACK[GenericFamily.SYMBOL] = FILE_FALLBACK[GenericFamily.SANS]


class FontRegistry:

    def __init__(self):
        self._fams: dict[tuple[str, GenericFamily], str] = {}

    def macro(self, font: FontInfo) -> str:
        key = (font.family, font.generic)
        if key not in self._fams:
            self._fams[key] = r"\pdcF" + alpha_id(len(self._fams))
        return self._fams[key]

    def preamble(self) -> str:
        lines = []
        for (family, generic), macro in self._fams.items():
            candidates = []
            for name in [family] + FALLBACKS[generic]:
                if name and name not in candidates and re.fullmatch(r"[\w .\-]+", name):
                    candidates.append(name)
            reg, bold, it, bi = FILE_FALLBACK[generic]
            code = (rf"\newfontfamily{macro}{{{reg}}}[BoldFont={bold},ItalicFont={it},"
                    rf"BoldItalicFont={bi}]")
            for name in reversed(candidates):
                code = (rf"\IfFontExistsTF{{{name}}}{{\newfontfamily{macro}{{{name}}}}}"
                        rf"{{{code}}}")
            lines.append(f"% {family} ({generic.value})")
            lines.append(code)
        return "\n".join(lines)


class StyleRegistry:

    def __init__(self, fonts: FontRegistry, colors: "ColorRegistry"):
        self.fonts = fonts
        self.colors = colors
        self._styles: dict[tuple, str] = {}
        self._defs: list[str] = []

    def macro(self, font: FontInfo, size: float, color: Color, superscript: bool = False,
              leading: float | None = None) -> str:
        size = round(size * 2) / 2 if size >= 4 else round(size, 1)
        key = (font.family, font.generic, font.bold, font.italic, size, color.hex,
               round(leading or size * 1.2, 1), superscript)
        if key in self._styles:
            return self._styles[key]
        name = r"\pdcS" + alpha_id(len(self._styles))
        fam = self.fonts.macro(font)
        parts = [fam, rf"\fontsize{{{num(size)}}}{{{num(leading or size * 1.2)}}}\selectfont"]
        parts.append(r"\bfseries" if font.bold else r"\mdseries")
        parts.append(r"\itshape" if font.italic else r"\upshape")
        if not color.is_black:
            parts.append(rf"\color{{{self.colors.name(color)}}}")
        self._defs.append(rf"\newcommand{name}{{{''.join(parts)}}}")
        self._styles[key] = name
        return name

    def preamble(self) -> str:
        return "\n".join(self._defs)


class ColorRegistry:
    def __init__(self):
        self._colors: dict[str, str] = {}

    def name(self, c: Color) -> str:
        if c.hex not in self._colors:
            self._colors[c.hex] = "pdcC" + alpha_id(len(self._colors))
        return self._colors[c.hex]

    def preamble(self) -> str:
        return "\n".join(rf"\definecolor{{{n}}}{{HTML}}{{{h}}}" for h, n in self._colors.items())


FIT_MACRO = r"""\newsavebox\pdcBox
\makeatletter
\newcommand\pdcFit[2]{\sbox\pdcBox{#2}\ifdim\wd\pdcBox>#1\relax
  \edef\pdc@r{\strip@pt\dimexpr 1pt*\dimexpr#1\relax/\wd\pdcBox\relax}%
  \scalebox{\pdc@r}[1]{\usebox\pdcBox}\else\usebox\pdcBox\fi}
\makeatother"""


def copy_assets(files: set[str], asset_root: Path, out_dir: Path) -> list[Path]:
    copied = []
    for rel in sorted(files):
        src = asset_root / rel
        if not src.exists():
            continue
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        copied.append(dst)
    return copied
