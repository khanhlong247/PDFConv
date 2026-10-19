from __future__ import annotations

import zipfile

import pytest
from docx import Document as load_docx

from pdfconv.application.dto import ConversionOptions, JobState, LatexMode
from pdfconv.container import build_container
from pdfconv.renderers.base import OutputFormat

from .conftest import HAS_XELATEX

CASES = ["text_paragraphs", "form_with_leaders", "table_grid", "two_columns", "rotated_page",
         "images", "scanned", "invisible_text", "mixed_sizes", "vectors", "special_chars",
         "annotations", "empty_pages", "corrupted", "png_image"]


@pytest.mark.parametrize("mode", [LatexMode.EXACT, LatexMode.FLOW])
@pytest.mark.parametrize("case", CASES)
def test_end_to_end(case, mode, cases, settings):
    c = build_container(settings)
    opts = ConversionOptions(latex_mode=mode, compile_latex=HAS_XELATEX, preview_docx=False)
    src = cases[case]
    job = c.jobs.run_sync(src.read_bytes(), src.name, opts)
    assert job.state is JobState.SUCCEEDED, job.error
    kinds = {a.kind for a in job.artifacts}
    assert {"zip", "latex", "docx", "input"} <= kinds
    job_dir = c.repo.job_dir(job.id)
    docx_path = job_dir / next(a.path for a in job.artifacts if a.kind == "docx")
    load_docx(docx_path)
    with zipfile.ZipFile(job_dir / next(a.path for a in job.artifacts if a.kind == "zip")) as z:
        names = z.namelist()
    assert any(n.endswith(".tex") for n in names) and any(n.endswith(".docx") for n in names)
    if HAS_XELATEX:
        assert "latex_pdf" in kinds, job.report.latex_log[-3000:]
        if mode is LatexMode.EXACT and job.report.fidelity.get("latex"):
            assert min(job.report.fidelity["latex"]) > 0.5


def test_encrypted_requires_password(cases, settings):
    c = build_container(settings)
    src = cases["encrypted"]
    job = c.jobs.run_sync(src.read_bytes(), src.name, ConversionOptions(compile_latex=False, preview_docx=False))
    assert job.state is JobState.FAILED and "mật khẩu" in job.error.lower()
    job = c.jobs.run_sync(src.read_bytes(), src.name,
                          ConversionOptions(password="secret", compile_latex=False, preview_docx=False))
    assert job.state is JobState.SUCCEEDED
    assert job.options["password"] == "***"


def test_single_format(cases, settings):
    c = build_container(settings)
    src = cases["text_paragraphs"]
    job = c.jobs.run_sync(src.read_bytes(), src.name,
                          ConversionOptions(formats=[OutputFormat.DOCX], preview_docx=False))
    kinds = {a.kind for a in job.artifacts}
    assert "docx" in kinds and "latex" not in kinds


def test_garbage_input_fails_cleanly(settings):
    c = build_container(settings)
    job = c.jobs.run_sync(b"this is not a document", "x.pdf", ConversionOptions())
    assert job.state is JobState.FAILED and job.error
