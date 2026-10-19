from __future__ import annotations

import pytest
from PIL import Image

from pdfconv.domain.errors import PasswordRequiredError, UnsupportedInputError
from pdfconv.domain.models import ImageRole
from pdfconv.infrastructure.pdf.assets import AssetWriter
from pdfconv.infrastructure.pdf.fonts import FontNormalizer
from pdfconv.infrastructure.pdf.input import InputNormalizer
from pdfconv.infrastructure.pdf.reader import PdfReader, ReaderConfig


def read(path, tmp_path, **cfg):
    return PdfReader(AssetWriter(tmp_path / "assets")).read(path.read_bytes(), path.name, ReaderConfig(**cfg))


@pytest.mark.parametrize("raw,flags,family,bold,italic", [
    ("ABCDEF+TimesNewRomanPS-BoldItalicMT", 0, "Times New Roman", True, True),
    ("TimesNewRomanPSMT", 4, "Times New Roman", False, False),
    ("Arial-BoldMT", 0, "Arial", True, False),
    ("Helvetica-Oblique", 0, "Arial", False, True),
    ("CMBX10", 0, "Latin Modern Roman", True, False),
    ("CMTI12", 0, "Latin Modern Roman", False, True),
    ("Calibri,Bold", 0, "Calibri", True, False),
    ("SitkaDisplay", 4, "Sitka Display", False, False),
    ("CourierNewPSMT", 8, "Courier New", False, False),
])
def test_font_normalizer(raw, flags, family, bold, italic):
    f = FontNormalizer().normalize(raw, flags)
    assert (f.family, f.bold, f.italic) == (family, bold, italic)


def test_text_and_fonts(cases, tmp_path):
    doc = read(cases["text_paragraphs"], tmp_path)
    page = doc.pages[0]
    text = " ".join(ln.text for ln in page.lines)
    assert "TIÊU ĐỀ" in text and "Phenikaa" in text
    assert any(s.font.bold for ln in page.lines for s in ln.spans)


def test_rotated_page_is_normalised(cases, tmp_path):
    page = read(cases["rotated_page"], tmp_path).pages[0]
    assert page.width > page.height
    assert any("xoay 90" in ln.text for ln in page.lines)
    assert any(not ln.is_horizontal for ln in page.lines)


def test_images_alpha_cmyk_rotation(cases, tmp_path):
    page = read(cases["images"], tmp_path).pages[0]
    assert len(page.images) == 5
    alphas = [im for im in page.images if im.has_alpha]
    assert alphas, "ảnh PNG RGBA phải giữ kênh alpha"
    for im in page.images:
        with Image.open(tmp_path / "assets" / im.file) as pil:
            assert pil.mode in ("RGB", "RGBA", "L")
    rotated = [im for im in page.images if im.bbox.height > im.bbox.width and im.bbox.x0 > 350]
    assert rotated and rotated[0].pixel_height > rotated[0].pixel_width
    assert any(im.role is ImageRole.BACKGROUND for im in page.images)


def test_encrypted(cases, tmp_path):
    with pytest.raises(PasswordRequiredError):
        read(cases["encrypted"], tmp_path)
    with pytest.raises(PasswordRequiredError):
        read(cases["encrypted"], tmp_path, password="wrong")
    doc = read(cases["encrypted"], tmp_path, password="secret")
    assert "Encrypted content" in doc.pages[0].lines[0].text


def test_scanned_page(cases, tmp_path):
    page = read(cases["scanned"], tmp_path).pages[0]
    assert page.is_scanned
    assert page.images[0].role is ImageRole.PAGE_SCAN


def test_invisible_text_skipped(cases, tmp_path):
    texts = [ln.text for ln in read(cases["invisible_text"], tmp_path).pages[0].lines]
    assert any("Visible" in t for t in texts)
    assert not any("HIDDEN" in t for t in texts)


def test_mixed_sizes(cases, tmp_path):
    sizes = [(round(p.width), round(p.height)) for p in read(cases["mixed_sizes"], tmp_path).pages]
    assert sizes == [(595, 842), (842, 595), (612, 792)]


def test_vectors(cases, tmp_path):
    page = read(cases["vectors"], tmp_path).pages[0]
    ops = {seg.op for s in page.shapes for seg in s.segments}
    assert {"c", "l"} <= ops
    assert any(s.dashes for s in page.shapes)
    assert any(s.fill_opacity < 1 for s in page.shapes)
    assert page.vector_layer is not None


def test_annotations_are_baked(cases, tmp_path):
    text = " ".join(ln.text for ln in read(cases["annotations"], tmp_path).pages[0].lines)
    assert "Free text annotation" in text
    assert "Filled value" in text


def test_table_detected(cases, tmp_path):
    page = read(cases["table_grid"], tmp_path).pages[0]
    assert len(page.tables) == 1
    t = page.tables[0]
    assert (t.n_rows, t.n_cols) == (5, 4)


def test_corrupted_pdf_is_repaired(cases, tmp_path):
    doc = read(cases["corrupted"], tmp_path)
    assert doc.pages and doc.pages[0].lines


def test_input_normalizer(cases):
    norm = InputNormalizer(10_000_000)
    out = norm.normalize(cases["png_image"].read_bytes(), "picture.png")
    assert out.pdf_bytes.startswith(b"%PDF") and out.source_kind == "image"
    with pytest.raises(UnsupportedInputError):
        norm.normalize(b"", "x.pdf")
    with pytest.raises(UnsupportedInputError):
        norm.normalize(b"hello world", "notes.docx")
    with pytest.raises(UnsupportedInputError):
        InputNormalizer(10).normalize(b"%PDF-1.7 " + b"x" * 100, "big.pdf")
