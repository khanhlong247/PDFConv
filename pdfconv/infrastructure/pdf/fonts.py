from __future__ import annotations

import re
from functools import lru_cache

from ...domain.models import FontInfo, GenericFamily

_SUBSET = re.compile(r"^[A-Z]{6}\+")
_PS_SUFFIX = re.compile(r"(PSMT|PS|MT|Std|Pro|LT|OT)$")
_BOLD = re.compile(r"(bold|black|heavy|semibold|demibold|demi|extrabold|ultrabold|bd$)", re.I)
_ITALIC = re.compile(r"(italic|oblique|slanted|ital|kursiv|it$)", re.I)


_KNOWN: dict[str, tuple[str, GenericFamily]] = {
    "timesnewroman": ("Times New Roman", GenericFamily.SERIF),
    "timesroman": ("Times New Roman", GenericFamily.SERIF),
    "times": ("Times New Roman", GenericFamily.SERIF),
    "nimbusromno9l": ("Times New Roman", GenericFamily.SERIF),
    "nimbusroman": ("Times New Roman", GenericFamily.SERIF),
    "texgyretermes": ("TeX Gyre Termes", GenericFamily.SERIF),
    "liberationserif": ("Liberation Serif", GenericFamily.SERIF),
    "arial": ("Arial", GenericFamily.SANS),
    "arialnarrow": ("Arial Narrow", GenericFamily.SANS),
    "arialunicodems": ("Arial Unicode MS", GenericFamily.SANS),
    "helvetica": ("Arial", GenericFamily.SANS),
    "helveticaneue": ("Helvetica Neue", GenericFamily.SANS),
    "nimbussans": ("Arial", GenericFamily.SANS),
    "nimbussanl": ("Arial", GenericFamily.SANS),
    "liberationsans": ("Liberation Sans", GenericFamily.SANS),
    "couriernew": ("Courier New", GenericFamily.MONO),
    "courier": ("Courier New", GenericFamily.MONO),
    "nimbusmono": ("Courier New", GenericFamily.MONO),
    "liberationmono": ("Liberation Mono", GenericFamily.MONO),
    "consolas": ("Consolas", GenericFamily.MONO),
    "lucidaconsole": ("Lucida Console", GenericFamily.MONO),
    "dejavusansmono": ("DejaVu Sans Mono", GenericFamily.MONO),
    "calibri": ("Calibri", GenericFamily.SANS),
    "calibrilight": ("Calibri Light", GenericFamily.SANS),
    "cambria": ("Cambria", GenericFamily.SERIF),
    "cambriamath": ("Cambria Math", GenericFamily.SERIF),
    "candara": ("Candara", GenericFamily.SANS),
    "georgia": ("Georgia", GenericFamily.SERIF),
    "garamond": ("Garamond", GenericFamily.SERIF),
    "bookantiqua": ("Book Antiqua", GenericFamily.SERIF),
    "palatinolinotype": ("Palatino Linotype", GenericFamily.SERIF),
    "palatino": ("Palatino Linotype", GenericFamily.SERIF),
    "bookmanoldstyle": ("Bookman Old Style", GenericFamily.SERIF),
    "centuryschoolbook": ("Century Schoolbook", GenericFamily.SERIF),
    "verdana": ("Verdana", GenericFamily.SANS),
    "tahoma": ("Tahoma", GenericFamily.SANS),
    "trebuchetms": ("Trebuchet MS", GenericFamily.SANS),
    "segoeui": ("Segoe UI", GenericFamily.SANS),
    "centurygothic": ("Century Gothic", GenericFamily.SANS),
    "comicsansms": ("Comic Sans MS", GenericFamily.SANS),
    "franklingothic": ("Franklin Gothic Medium", GenericFamily.SANS),
    "gillsans": ("Gill Sans MT", GenericFamily.SANS),
    "roboto": ("Roboto", GenericFamily.SANS),
    "opensans": ("Open Sans", GenericFamily.SANS),
    "lato": ("Lato", GenericFamily.SANS),
    "montserrat": ("Montserrat", GenericFamily.SANS),
    "sourcesanspro": ("Source Sans Pro", GenericFamily.SANS),
    "notosans": ("Noto Sans", GenericFamily.SANS),
    "notoserif": ("Noto Serif", GenericFamily.SERIF),
    "dejavusans": ("DejaVu Sans", GenericFamily.SANS),
    "dejavuserif": ("DejaVu Serif", GenericFamily.SERIF),
    "symbol": ("Symbol", GenericFamily.SYMBOL),
    "symbolmt": ("Symbol", GenericFamily.SYMBOL),
    "wingdings": ("Wingdings", GenericFamily.SYMBOL),
    "webdings": ("Webdings", GenericFamily.SYMBOL),
    "zapfdingbats": ("ZapfDingbats", GenericFamily.SYMBOL),
    "msgothic": ("MS Gothic", GenericFamily.SANS),
    "msmincho": ("MS Mincho", GenericFamily.SERIF),
    "simsun": ("SimSun", GenericFamily.SERIF),
    "simhei": ("SimHei", GenericFamily.SANS),
    "mingliu": ("MingLiU", GenericFamily.SERIF),
    "malgungothic": ("Malgun Gothic", GenericFamily.SANS),
    "lmroman": ("Latin Modern Roman", GenericFamily.SERIF),
    "lmsans": ("Latin Modern Sans", GenericFamily.SANS),
    "lmmono": ("Latin Modern Mono", GenericFamily.MONO),
}


_TEX_CM = [
    ("cmbxti", "Latin Modern Roman", GenericFamily.SERIF, True, True),
    ("cmbx", "Latin Modern Roman", GenericFamily.SERIF, True, False),
    ("cmb", "Latin Modern Roman", GenericFamily.SERIF, True, False),
    ("cmti", "Latin Modern Roman", GenericFamily.SERIF, False, True),
    ("cmsl", "Latin Modern Roman", GenericFamily.SERIF, False, True),
    ("cmmi", "Latin Modern Roman", GenericFamily.SERIF, False, True),
    ("cmssbx", "Latin Modern Sans", GenericFamily.SANS, True, False),
    ("cmss", "Latin Modern Sans", GenericFamily.SANS, False, False),
    ("cmtt", "Latin Modern Mono", GenericFamily.MONO, False, False),
    ("cmsy", "Latin Modern Math", GenericFamily.SYMBOL, False, False),
    ("cmex", "Latin Modern Math", GenericFamily.SYMBOL, False, False),
    ("cmr", "Latin Modern Roman", GenericFamily.SERIF, False, False),
    ("sfrm", "Latin Modern Roman", GenericFamily.SERIF, False, False),
    ("sfbx", "Latin Modern Roman", GenericFamily.SERIF, True, False),
    ("sfti", "Latin Modern Roman", GenericFamily.SERIF, False, True),
]

_SANS_HINT = re.compile(r"(sans|arial|helvet|calibri|verdana|tahoma|segoe|gothic|grotesk|roboto|lato)", re.I)
_MONO_HINT = re.compile(r"(mono|courier|consol|code|typewriter)", re.I)
_SYMBOL_HINT = re.compile(r"(symbol|dingbat|wingding|webding|math)", re.I)


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _split_camel(s: str) -> str:
    s = re.sub(r"[_]+", " ", s)
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class FontNormalizer:

    @lru_cache(maxsize=1024)
    def normalize(self, raw_name: str, flags: int = 0) -> FontInfo:
        name = _SUBSET.sub("", raw_name or "").strip() or "Unknown"
        parts = re.split(r"[-,]", name, maxsplit=1)
        base = parts[0].strip() or name
        style = parts[1].strip() if len(parts) > 1 else ""
        base_clean = _PS_SUFFIX.sub("", base)
        key = _key(base_clean)

        bold = bool(flags & 16) or bool(_BOLD.search(style)) or bool(re.search(r"bold|black|heavy", base, re.I))
        italic = bool(flags & 2) or bool(_ITALIC.search(style)) or bool(re.search(r"italic|oblique", base, re.I))

        for prefix, fam, gen, b, i in _TEX_CM:
            if key.startswith(prefix) and (len(key) == len(prefix) or key[len(prefix)].isdigit()):
                return FontInfo(fam, gen, bold or b, italic or i, raw_name)

        hit = _KNOWN.get(key)
        if hit is None:
            stripped = re.sub(r"(Bold|Italic|Oblique|Regular|Roman|Light|Medium|Black|Semibold|Narrow)+$",
                              "", base_clean)
            hit = _KNOWN.get(_key(stripped))
            if hit is None:
                for k, v in sorted(_KNOWN.items(), key=lambda kv: -len(kv[0])):
                    if len(k) >= 5 and key.startswith(k):
                        hit = v
                        break
            if hit is None and stripped:
                base_clean = stripped
        if hit:
            family, generic = hit
        else:
            family = _split_camel(base_clean) or "Unknown"
            if flags & 8 or _MONO_HINT.search(name):
                generic = GenericFamily.MONO
            elif _SYMBOL_HINT.search(name):
                generic = GenericFamily.SYMBOL
            elif _SANS_HINT.search(name):
                generic = GenericFamily.SANS
            elif flags & 4:
                generic = GenericFamily.SERIF
            else:
                generic = GenericFamily.SANS
        return FontInfo(family, generic, bold, italic, raw_name)
