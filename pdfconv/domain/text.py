from __future__ import annotations

import re
import unicodedata


PUA_MAP = {
    "": "•", "": "•", "": "▪", "": "■", "": "□",
    "": "❑", "": "□", "": "☑", "": "☒", "": "✓",
    "": "➢", "": "❖", "": "→", "": "➔", "": "○",
    "": "◊", "": "-", "": " ", "": "●", "": "●",
    "": "⇨", "": "−",
}

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
             "ﬅ": "st", "ﬆ": "st"}

LEADER_CHARS = frozenset(".…_·‥")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f﻿​]")

LIST_MARKER = re.compile(r"^\s*(?:\d{1,3}[.)]|[a-zA-Z][.)]|[ivxlcIVXLC]{1,5}[.)]|[-–•▪●○◦*+➢❖□■✓])\s")


_SPACES = frozenset("              　")


def clean_char(c: str) -> str:
    if c in _SPACES:
        return " "
    if c in PUA_MAP:
        return PUA_MAP[c]
    if c in LIGATURES:
        return LIGATURES[c]
    if c == "­":
        return ""
    if c == "\t":
        return " "
    if _CTRL.match(c):
        return ""
    if "" <= c <= "":
        return "□"
    return c


def clean_text(s: str) -> str:
    return unicodedata.normalize("NFC", "".join(clean_char(c) for c in s))


def strip_xml_invalid(s: str) -> str:
    return "".join(c for c in s if c in "\t\n\r" or ("\x20" <= c <= "퟿")
                   or ("" <= c <= "�") or ("\U00010000" <= c <= "\U0010ffff"))
