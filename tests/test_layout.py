from __future__ import annotations

from pdfconv.analysis.layout_analyzer import LayoutAnalyzer
from pdfconv.domain.layout import (Align, ParagraphBlock, ParagraphKind, SegmentKind, TableBlock)
from pdfconv.infrastructure.pdf.assets import AssetWriter
from pdfconv.infrastructure.pdf.reader import PdfReader, ReaderConfig


def layout(path, tmp_path):
    doc = PdfReader(AssetWriter(tmp_path / "assets")).read(path.read_bytes(), path.name, ReaderConfig())
    return LayoutAnalyzer().analyze(doc)


def blocks(lp):
    return [b for band in lp.bands for rg in band.regions for b in rg.blocks]


def test_paragraphs_are_merged(cases, tmp_path):
    lp = layout(cases["text_paragraphs"], tmp_path).pages[0]
    paras = [b for b in blocks(lp) if isinstance(b, ParagraphBlock)]
    multi = [p for p in paras if len(p.rows) >= 3]
    assert len(multi) == 2, "mỗi đoạn văn nhiều dòng phải được gộp thành một khối"
    assert all(p.align in (Align.LEFT, Align.JUSTIFY) for p in multi)
    text = "".join(r.text for p in multi for r in p.runs())
    assert "Phenikaa tuyển sinh" in text and "brown fox" in text
    title = paras[0]
    assert len(title.rows) == 1 and title.runs()[0].font.bold


def test_leaders_become_tab_segments(cases, tmp_path):
    lp = layout(cases["form_with_leaders"], tmp_path).pages[0]
    tabbed = [b for b in blocks(lp) if isinstance(b, ParagraphBlock) and b.kind is ParagraphKind.TABBED]
    assert len(tabbed) >= 4
    first = tabbed[0].rows[0].segments
    kinds = [s.kind for s in first]
    assert kinds == [SegmentKind.TEXT, SegmentKind.LEADER, SegmentKind.TEXT, SegmentKind.LEADER]
    assert first[2].text.startswith("Giới tính")
    underscores = [s for b in tabbed for s in b.rows[0].segments if s.leader_char == "_"]
    assert underscores


def test_table_block_with_cells(cases, tmp_path):
    lp = layout(cases["table_grid"], tmp_path).pages[0]
    tables = [b for b in blocks(lp) if isinstance(b, TableBlock)]
    assert len(tables) == 1
    cells = {(c.row, c.col): c for c in tables[0].cells}
    head = "".join(r.text for p in cells[(0, 1)].paragraphs for r in p.runs())
    assert head == "Họ và tên"
    assert "Nguyễn Văn A" in "".join(r.text for p in cells[(1, 1)].paragraphs for r in p.runs())


def test_two_columns_detected(cases, tmp_path):
    lp = layout(cases["two_columns"], tmp_path).pages[0]
    assert any(b.columns == 2 for b in lp.bands)
    title_band = lp.bands[0]
    assert title_band.columns == 1


def test_images_inline_and_anchored(cases, tmp_path):
    lp = layout(cases["images"], tmp_path).pages[0]
    assert lp.anchored, "ảnh nền dưới chữ phải được đặt nổi"


def test_text_boxes_from_frames(cases, tmp_path):
    lp = layout(cases["vectors"], tmp_path).pages[0]
    assert not lp.text_boxes
