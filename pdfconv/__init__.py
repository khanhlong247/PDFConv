"""pdfconv – chuyển PDF (và ảnh/XPS/EPUB) sang LaTeX và DOCX.

Kiến trúc phân lớp:
    domain/          mô hình dữ liệu thuần (không phụ thuộc thư viện ngoài)
    infrastructure/  đọc PDF (PyMuPDF), toolchain biên dịch, lưu trữ job
    analysis/        phân tích bố cục: dòng, tab, đoạn văn, cột, bảng
    renderers/       sinh LaTeX (exact/flow) và DOCX
    application/     pipeline chuyển đổi + dịch vụ job
    presentation/    REST API, giao diện web, CLI
"""

__version__ = "2.0.0"
