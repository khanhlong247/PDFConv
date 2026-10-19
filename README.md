# pdfconv – chuyển PDF sang LaTeX và DOCX

Chuyển PDF (và ảnh, XPS, EPUB) thành **LaTeX** (.tex + thư mục `images/`) và **Word (.docx)**,
giữ bố cục, font, logo, ảnh chìm, bảng, dòng chấm điền thông tin. Có giao diện web tại
**http://127.0.0.1:8000**, REST API và dòng lệnh.

## Chạy nhanh

### Docker (khuyến nghị)

```bash
docker compose up -d --build
# mở http://127.0.0.1:8000
```

Compose gồm hai khối:

| Service | Vai trò | Thành phần |
|---|---|---|
| `toolchain` | Môi trường đọc/biên dịch LaTeX, PDF | TeX Live (XeLaTeX, fontspec, TikZ…), LibreOffice, poppler, ghostscript, font Liberation/DejaVu/TeX Gyre/Latin Modern |
| `web` | Giao diện + pipeline chuyển đổi | Python, PyMuPDF, python-docx, Tesseract OCR (vie, eng) |

- `web` chỉ công bố cổng `127.0.0.1:8000`, nên chỉ máy hiện tại truy cập được.
- `toolchain` chỉ mở cổng trong mạng nội bộ của compose.
- Dữ liệu job được lưu trong volume `pdfconv-data`.

Tuỳ chọn khi build:

- Thêm font Times New Roman/Arial của Microsoft (cần chấp nhận EULA): đặt `INSTALL_MSFONTS: "true"` trong `docker-compose.yml`. Nếu không, hệ thống dùng Liberation Serif/Sans, là font có kích thước chữ tương đương.
- Bỏ LibreOffice để image nhỏ hơn: `WITH_LIBREOFFICE: "false"`. Khi đó giao diện không còn ảnh xem trước của DOCX.
- Chạy một container duy nhất: `docker build --target standalone -t pdfconv .`, rồi `docker run -p 127.0.0.1:8000:8000 pdfconv`.

### Chạy trực tiếp (không Docker)

```bash
pip install -r requirements.txt
python -m pdfconv serve            # http://127.0.0.1:8000
```

- Cần XeLaTeX (TeX Live hoặc MiKTeX) để biên dịch LaTeX ra PDF.
- Cần LibreOffice, hoặc Microsoft Word trên Windows, để xem trước DOCX.
- Thiếu công cụ nào thì bước tương ứng được bỏ qua, file .tex/.docx vẫn được tạo.

### Dòng lệnh

```bash
python -m pdfconv convert a.pdf b.pdf -o ket-qua/ --latex-mode exact --formats latex,docx
python -m pdfconv convert scan.pdf --ocr --ocr-language vie+eng
python -m pdfconv convert bao-mat.pdf --password 1234 --no-preview
```

## Kiến trúc phân lớp

```
pdfconv/
├── domain/            Mô hình thuần, không phụ thuộc thư viện
│   ├── geometry.py      Rect, Point
│   ├── models.py        Document, Page, TextLine/Span/Glyph, ImageElement, Shape, TableElement
│   ├── layout.py        Mô hình luồng: Band, Region, ParagraphBlock, Segment(TEXT|LEADER), TableBlock, TextBoxBlock
│   ├── text.py          Chuẩn hoá ký tự (NBSP, ligature, ký tự Symbol/Wingdings)
│   └── errors.py        Lỗi nghiệp vụ
├── infrastructure/    Giao tiếp thư viện/hệ thống
│   ├── pdf/             input.py (chuẩn hoá đầu vào), reader.py, fonts.py, images.py,
│   │                    graphics.py, rasterizer.py, ocr.py, assets.py
│   ├── toolchain/       local.py (xelatex, LibreOffice, Word), remote.py (gọi service toolchain)
│   └── storage/         job_store.py (job.json + thư mục job)
├── analysis/          Phân tích bố cục: rows.py, paragraphs.py, columns.py, boxes.py, layout_analyzer.py
├── renderers/         Sinh đầu ra (cùng giao diện DocumentRenderer)
│   ├── latex/           exact.py, flow.py, common.py (escape, font dự phòng, kiểu chữ)
│   └── docx/            renderer.py, ooxml.py
├── application/       dto.py (ConversionOptions, Job, Report…), pipeline.py, job_service.py
├── presentation/      api.py (FastAPI), cli.py, web/ (HTML/CSS/JS)
├── container.py       Lắp ráp phụ thuộc
└── config.py          Cấu hình qua biến môi trường PDFCONV_*
toolchain_service/     Dịch vụ biên dịch chạy trong container riêng
tests/                 Bộ kiểm thử với PDF sinh tự động
```

Luồng xử lý:

```
upload → InputNormalizer → PdfReader → LayoutAnalyzer → Renderer → Toolchain → so sánh → zip
```

- **InputNormalizer**: chuyển mọi đầu vào sang PDF.
- **PdfReader**: đọc PDF thành `Document`.
- **LayoutAnalyzer**: chuyển `Document` thành `LayoutDocument`.
- **Renderer**: sinh LaTeX exact, LaTeX flow hoặc DOCX.
- **Toolchain**: biên dịch hoặc xuất ra PDF.
- **So sánh**: đo độ giống thị giác giữa bản gốc và bản đầu ra.

## Đầu vào và đầu ra chuẩn hoá

**Đầu vào** `ConversionOptions` (JSON). Ví dụ:

```json
{"formats": ["latex", "docx"], "latex_mode": "exact", "compile_latex": true,
 "preview_docx": true, "ocr": false, "ocr_language": "vie+eng", "password": null,
 "max_pages": null, "detect_tables": true, "detect_columns": true}
```

**Đầu ra** là `Job`, gồm:

- trạng thái và tiến độ;
- danh sách `artifacts` (zip, .tex, PDF biên dịch, .docx, PDF xem trước);
- `report`: thông tin từng trang, cảnh báo, thời gian, độ giống từng trang, ảnh xem trước và log biên dịch.

Thư mục một job:

```
data/jobs/<id>/
├── job.json
├── input/<tên>.pdf
├── output/latex/<tên>.tex, images/…, <tên>.pdf
├── output/docx/<tên>.docx
├── previews/original_001.png, latex_001.png, docx_001.png
└── <tên>-pdfconv.zip
```

## REST API

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/health` | Công cụ hiện có (XeLaTeX, xem trước DOCX, OCR) và giới hạn |
| POST | `/api/jobs` | multipart: `files` (nhiều file) và `options` (chuỗi JSON). Trả về danh sách job |
| GET | `/api/jobs`, `/api/jobs/{id}` | Trạng thái và kết quả |
| GET | `/api/jobs/{id}/files/{path}?download=1` | Tải file kết quả |
| DELETE | `/api/jobs/{id}` | Xoá job |

Tài liệu OpenAPI: http://127.0.0.1:8000/docs

## Các trường hợp PDF được xử lý

| Trường hợp | Cách xử lý |
|---|---|
| Logo, ảnh chìm có kênh alpha (SMask) | Tự ghép SMask thành PNG trong suốt. Ảnh nằm dưới chữ (dựa vào thứ tự vẽ) được đặt sau chữ |
| Ảnh CMYK, Indexed, xám, JPX, JBIG2, stencil mask, ảnh inline | Chuyển sang RGB/RGBA; giữ nguyên JPEG gốc khi có thể |
| Ảnh xoay, lật, nghiêng | Áp ma trận hiển thị lên ảnh |
| Ảnh trùng lặp | Khử trùng theo nội dung |
| Trang có `/Rotate`, khổ giấy khác nhau | Chuẩn hoá hướng trang. Mỗi trang giữ kích thước riêng (LaTeX exact; DOCX dùng section riêng) |
| Font subset, hậu tố PostScript, font TeX (CMR…) | Chuẩn hoá tên họ font, đậm, nghiêng. LaTeX chọn font tồn tại lúc biên dịch theo chuỗi dự phòng |
| Ký tự đặc biệt | Escape đầy đủ ký tự đặc biệt LaTeX; NBSP, ligature, ký tự Symbol/Wingdings, ký tự XML không hợp lệ |
| Chữ ẩn (lớp OCR có sẵn) | Bỏ qua, hoặc dùng làm chữ khi bật OCR |
| Trang scan | Giữ dạng ảnh, hoặc OCR bằng Tesseract (Docker có sẵn tiếng Việt) |
| Chú thích, ô form đã điền | "Bake" vào nội dung trang trước khi trích xuất |
| PDF mã hoá | Hỗ trợ mật khẩu; mật khẩu không được lưu vào job |
| PDF hỏng xref/trailer | MuPDF tự sửa; cảnh báo hiện trong báo cáo |
| Vector (đường, Bezier, nét đứt, độ mờ, even-odd) | LaTeX exact: vẽ bằng TikZ. DOCX/flow: lớp vector raster trong suốt đặt sau chữ |
| Trang đồ hoạ phức tạp (gradient, hàng nghìn hình) | Raster hoá lớp vector |
| Bảng có đường kẻ, ô gộp | Thành bảng Word thật / `tabular` |
| Khung chứa chữ (ô ảnh 4x6, ô mã mẫu) | Thành text box nổi đúng vị trí |
| Dòng chấm, gạch dưới để điền | Tab stop có dấu chấm dẫn (DOCX) / `\pdcLead` (LaTeX flow) |
| Đoạn văn nhiều dòng, căn trái/giữa/phải/đều, thụt dòng | Gộp dòng, nhận diện căn lề và thụt lề |
| Bố cục 2–3 cột | Section nhiều cột (DOCX) / `multicols` (LaTeX) |
| Đầu vào ảnh, XPS, EPUB | Chuyển sang PDF trước khi xử lý |

### Hai kiểu LaTeX

- **exact**: mỗi từ đặt đúng toạ độ gốc; ảnh, vector và chữ theo đúng thứ tự vẽ. Độ giống với bản gốc thường đạt 95–98%. Phù hợp để in lại hoặc lưu trữ.
- **flow**: đoạn văn, tab, bảng `tabular`, nhiều cột. Dễ sửa nội dung, độ giống thấp hơn một chút.

DOCX luôn ở dạng chỉnh sửa được:

- chữ là đoạn văn thật;
- dòng chấm là tab có dấu chấm dẫn;
- bảng là bảng Word thật;
- logo, ảnh chìm và đường kẻ vector nằm nổi sau chữ, đúng toạ độ.

## Kiểm thử

```bash
pip install -r requirements-dev.txt
pytest
```

Bộ kiểm thử tự sinh PDF cho từng trường hợp khó: đoạn văn, form có dòng chấm, bảng, hai cột, trang xoay, ảnh alpha/CMYK/xoay, PDF mã hoá, trang scan, chữ ẩn, nhiều khổ giấy, vector, ký tự đặc biệt, annotation và form, trang trắng, PDF hỏng, đầu vào ảnh.

Mỗi trường hợp được chạy toàn bộ pipeline ở cả hai kiểu LaTeX, có biên dịch XeLaTeX nếu máy có. Ngoài ra có test cho API và dịch vụ toolchain.

## Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PDFCONV_HOST` / `PDFCONV_PORT` | `127.0.0.1` / `8000` | Địa chỉ web |
| `PDFCONV_DATA_DIR` | `./data` | Thư mục lưu job |
| `PDFCONV_TOOLCHAIN_URL` | trống | URL dịch vụ toolchain; trống thì chỉ dùng công cụ trên máy |
| `PDFCONV_MAX_UPLOAD_MB` / `PDFCONV_MAX_PAGES` | `100` / `300` | Giới hạn đầu vào |
| `PDFCONV_TOOLCHAIN_TIMEOUT` | `240` | Thời gian tối đa cho một lần biên dịch (giây) |
| `PDFCONV_VECTOR_DPI` / `PDFCONV_PREVIEW_DPI` | `150` / `72` | Độ phân giải lớp vector và ảnh xem trước |
| `PDFCONV_ENABLE_WORD` | `1` | Cho phép dùng Microsoft Word trên Windows để xem trước DOCX |

## Giới hạn đã biết

- Font không có trên máy biên dịch sẽ được thay bằng font tương đương.
  - Ở LaTeX exact, chữ quá rộng được co ngang cho vừa chỗ.
  - Ở DOCX, Word tự thay font.
- Chữ xoay chéo, chữ dọc (CJK) và công thức toán được giữ đúng vị trí ở LaTeX exact. Ở chế độ luồng (flow, DOCX), chúng thành chữ ngang thường.
- Trong DOCX, đường kẻ không thuộc bảng là ảnh nền: sửa chữ làm dòng xê dịch thì đường kẻ không đi theo.
- Mỗi lần chỉ xử lý một job, vì PyMuPDF không an toàn đa luồng. Các job còn lại xếp hàng chờ.
