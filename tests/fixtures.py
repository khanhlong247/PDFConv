from __future__ import annotations

import io
import os
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\times.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
BOLD_CANDIDATES = [
    r"C:\Windows\Fonts\timesbd.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]

VI = ("Con cáo nâu nhanh nhẹn nhảy qua chú chó lười biếng, trong khi hội đồng xem xét từng đơn đăng ký một cách cẩn thận và công bằng theo các quy định tuyển sinh đã được công bố.")
EN = ("The quick brown fox jumps over the lazy dog while the committee reviews every application "
      "carefully and fairly according to the published admission regulations. ")


def _font(cands: list[str]) -> str | None:
    return next((c for c in cands if os.path.exists(c)), None)


def _page_font(page: pymupdf.Page, bold: bool = False) -> str:
    f = _font(BOLD_CANDIDATES if bold else FONT_CANDIDATES)
    name = "F1" if not bold else "F2"
    if f:
        page.insert_font(fontname=name, fontfile=f)
        return name
    return "tibo" if bold else "tiro"


def has_unicode_font() -> bool:
    return _font(FONT_CANDIDATES) is not None


def _save(doc: pymupdf.Document, path: Path, **kw) -> Path:
    doc.save(path, **kw)
    doc.close()
    return path


def text_paragraphs(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    fn, fb = _page_font(page), _page_font(page, bold=True)
    page.insert_text((72, 80), "TIÊU ĐỀ VĂN BẢN THỬ NGHIỆM", fontname=fb, fontsize=16)
    r = pymupdf.Rect(72, 110, 523, 400)
    page.insert_textbox(r, (VI * 3).strip(), fontname=fn, fontsize=11, align=pymupdf.TEXT_ALIGN_JUSTIFY)
    page.insert_textbox(pymupdf.Rect(72, 420, 523, 600), (EN * 3).strip(), fontname=fn, fontsize=11)
    return _save(doc, path)


def form_with_leaders(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    fn = _page_font(page)
    y = 90
    for label, second in [("Họ và tên: ", "Giới tính: "), ("Ngày sinh: ", "Nơi sinh: "),
                          ("Địa chỉ: ", None), ("Số điện thoại: ", "Email: ")]:
        page.insert_text((60, y), label + "." * 40 + ((" " + second + "." * 25) if second else "." * 60),
                         fontname=fn, fontsize=11)
        y += 20
    page.insert_text((60, y + 10), "Ký tên: ________________", fontname=fn, fontsize=11)
    return _save(doc, path)


def table_grid(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    fn = _page_font(page)
    xs, ys = [60, 140, 300, 420, 535], [100 + 24 * i for i in range(6)]
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), width=0.8)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), width=0.8)
    heads = ["STT", "Họ và tên", "Năm sinh", "Ghi chú"]
    for c, h in enumerate(heads):
        page.insert_text((xs[c] + 4, ys[0] + 16), h, fontname=fn, fontsize=10)
    for r in range(1, 5):
        for c, v in enumerate([str(r), f"Nguyễn Văn {chr(64 + r)}", str(1990 + r), "—"]):
            page.insert_text((xs[c] + 4, ys[r] + 16), v, fontname=fn, fontsize=10)
    page.insert_text((60, 90), "Bảng danh sách", fontname=fn, fontsize=12)
    return _save(doc, path)


def two_columns(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    fn, fb = _page_font(page), _page_font(page, bold=True)
    page.insert_text((140, 70), "Bài báo hai cột: phân tích bố cục", fontname=fb, fontsize=16)
    page.insert_textbox(pymupdf.Rect(50, 100, 290, 780), (VI + EN) * 5, fontname=fn, fontsize=9.5,
                        align=pymupdf.TEXT_ALIGN_JUSTIFY)
    page.insert_textbox(pymupdf.Rect(305, 100, 545, 780), (EN + VI) * 5, fontname=fn, fontsize=9.5,
                        align=pymupdf.TEXT_ALIGN_JUSTIFY)
    return _save(doc, path)


def rotated_page(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    fn = _page_font(page)
    page.insert_text((72, 100), "Trang này được xoay 90 độ.", fontname=fn, fontsize=14)
    page.insert_text((300, 500), "Chữ xoay dọc", fontname=fn, fontsize=12, rotate=90)
    page.set_rotation(90)
    return _save(doc, path)


def _png_rgba() -> bytes:
    im = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((10, 10, 190, 110), fill=(220, 80, 30, 200), outline=(20, 40, 120, 255), width=6)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _jpeg_cmyk() -> bytes:
    im = Image.new("CMYK", (160, 100), (0, 200, 200, 0))
    ImageDraw.Draw(im).rectangle((20, 20, 140, 80), fill=(200, 0, 0, 0))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def images(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    fn = _page_font(page)
    page.insert_text((72, 60), "Ảnh có kênh alpha, CMYK, xám và ảnh xoay:", fontname=fn, fontsize=12)
    page.insert_image(pymupdf.Rect(72, 80, 272, 200), stream=_png_rgba())
    page.insert_image(pymupdf.Rect(300, 80, 460, 180), stream=_jpeg_cmyk())
    gray = Image.linear_gradient("L").resize((128, 64))
    buf = io.BytesIO()
    gray.save(buf, "PNG")
    page.insert_image(pymupdf.Rect(72, 240, 328, 368), stream=buf.getvalue())
    page.insert_image(pymupdf.Rect(360, 240, 480, 440), stream=_png_rgba(), rotate=90)
    # ảnh nền lớn nằm dưới chữ (kiểu watermark)
    page.insert_image(pymupdf.Rect(100, 480, 500, 760), stream=_png_rgba(), overlay=False)
    page.insert_text((150, 620), "Chữ đè lên ảnh nền", fontname=fn, fontsize=14)
    return _save(doc, path)


def encrypted(path: Path, password: str = "secret") -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Encrypted content", fontname="helv", fontsize=14)
    return _save(doc, path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw="owner-pw")


def scanned(path: Path) -> Path:
    src = pymupdf.open()
    sp = src.new_page()
    sp.insert_text((72, 100), "Scanned page text", fontname="helv", fontsize=20)
    pix = sp.get_pixmap(dpi=100)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    src.close()
    return _save(doc, path)


def invisible_text(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Visible line", fontname="helv", fontsize=12)
    page.insert_text((72, 140), "HIDDEN OCR LAYER", fontname="helv", fontsize=12, render_mode=3)
    return _save(doc, path)


def mixed_sizes(path: Path) -> Path:
    doc = pymupdf.open()
    for w, h, label in [(595, 842, "A4 portrait"), (842, 595, "A4 landscape"), (612, 792, "Letter")]:
        p = doc.new_page(width=w, height=h)
        p.insert_text((72, 100), label, fontname="helv", fontsize=18)
    return _save(doc, path)


def vectors(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    shape = page.new_shape()
    shape.draw_bezier((80, 300), (150, 100), (250, 500), (330, 300))
    shape.finish(color=(0.8, 0, 0), width=2)
    shape.draw_circle((420, 200), 60)
    shape.finish(color=(0, 0, 0.6), fill=(0.6, 0.8, 1), fill_opacity=0.5, width=1.5)
    shape.draw_line((60, 600), (540, 600))
    shape.finish(color=(0, 0, 0), dashes="[6 3] 0", width=1)
    shape.draw_polyline([(100, 650), (200, 720), (300, 650), (400, 720)])
    shape.finish(color=(0, 0.5, 0), width=3, lineCap=1, lineJoin=1, closePath=False)
    shape.draw_rect(pymupdf.Rect(60, 60, 540, 780))
    shape.finish(color=(0.2, 0.2, 0.2), width=4)
    shape.commit()
    page.insert_text((80, 560), "Vector graphics test", fontname="helv", fontsize=14)
    return _save(doc, path)


def special_chars(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    fn = _page_font(page)
    lines = [r"LaTeX specials: \ { } $ & # ^ _ % ~ < > |",
             "Tiếng Việt: Ấn Độ, Đà Nẵng, Huế, ỷ lại, ữ, ộ, ỡ – “ngoặc kép” … ©",
             "Ligatures: office affine flow — file",
             "Chỉ số: E = mc2 và H2O"]
    for i, t in enumerate(lines):
        page.insert_text((60, 100 + 24 * i), t, fontname=fn, fontsize=12)
    page.insert_text((157, 166), "2", fontname=fn, fontsize=7)    # số mũ
    return _save(doc, path)


def annotations(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "Form and annotation test", fontname="helv", fontsize=14)
    page.add_freetext_annot(pymupdf.Rect(72, 100, 300, 140), "Free text annotation", fontsize=11)
    w = pymupdf.Widget()
    w.field_name = "name"
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.rect = pymupdf.Rect(72, 160, 300, 185)
    w.field_value = "Filled value"
    page.add_widget(w)
    return _save(doc, path)


def empty_pages(path: Path) -> Path:
    doc = pymupdf.open()
    doc.new_page()
    p = doc.new_page()
    p.insert_text((72, 100), "Only the second page has text", fontname="helv", fontsize=12)
    doc.new_page()
    return _save(doc, path)


def corrupted(path: Path) -> Path:
    good = text_paragraphs(path.with_name("_good.pdf"))
    data = good.read_bytes()
    cut = data.rfind(b"xref")
    path.write_bytes(data[:cut] + b"xref\n0 999\ngarbage\n%%EOF")
    good.unlink()
    return path


def png_image(path: Path) -> Path:
    path.write_bytes(_png_rgba())
    return path


ALL_CASES = {
    "text_paragraphs": text_paragraphs,
    "form_with_leaders": form_with_leaders,
    "table_grid": table_grid,
    "two_columns": two_columns,
    "rotated_page": rotated_page,
    "images": images,
    "scanned": scanned,
    "invisible_text": invisible_text,
    "mixed_sizes": mixed_sizes,
    "vectors": vectors,
    "special_chars": special_chars,
    "annotations": annotations,
    "empty_pages": empty_pages,
    "corrupted": corrupted,
}
