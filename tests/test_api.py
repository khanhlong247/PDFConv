from __future__ import annotations

import io
import json
import time
import zipfile

from fastapi.testclient import TestClient

from pdfconv.container import build_container
from pdfconv.presentation.api import create_app

from .conftest import HAS_XELATEX


def _client(settings) -> TestClient:
    return TestClient(create_app(build_container(settings)))


def _wait(client: TestClient, job_id: str, timeout: float = 180) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed"):
            return job
        time.sleep(0.3)
    raise TimeoutError(job_id)


def test_index_and_health(settings):
    c = _client(settings)
    r = c.get("/")
    assert r.status_code == 200 and "pdfconv" in r.text
    assert c.get("/static/app.js").status_code == 200
    h = c.get("/api/health").json()
    assert h["toolchain"]["latex"] == HAS_XELATEX
    assert "ocr" in h and "limits" in h


def test_upload_convert_download(settings, cases):
    c = _client(settings)
    opts = {"formats": ["latex", "docx"], "latex_mode": "exact", "compile_latex": HAS_XELATEX,
            "preview_docx": False}
    files = [("files", ("form.pdf", cases["form_with_leaders"].read_bytes(), "application/pdf")),
             ("files", ("bang.pdf", cases["table_grid"].read_bytes(), "application/pdf"))]
    r = c.post("/api/jobs", files=files, data={"options": json.dumps(opts)})
    assert r.status_code == 202, r.text
    jobs = r.json()
    assert len(jobs) == 2
    for j in jobs:
        done = _wait(c, j["id"])
        assert done["state"] == "succeeded", done["error"]
        zip_art = next(a for a in done["artifacts"] if a["kind"] == "zip")
        z = c.get(f"/api/jobs/{j['id']}/files/{zip_art['path']}?download=1")
        assert z.status_code == 200 and "attachment" in z.headers["content-disposition"]
        names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
        assert any(n.endswith(".docx") for n in names)
        preview = done["report"]["previews"][0]["original"]
        assert c.get(f"/api/jobs/{j['id']}/files/{preview}").headers["content-type"] == "image/png"
    assert len(c.get("/api/jobs").json()) == 2
    assert c.delete(f"/api/jobs/{jobs[0]['id']}").status_code == 204
    assert c.get(f"/api/jobs/{jobs[0]['id']}").status_code == 404


def test_bad_requests(settings):
    c = _client(settings)
    r = c.post("/api/jobs", files=[("files", ("a.pdf", b"%PDF-1.4", "application/pdf"))],
               data={"options": json.dumps({"formats": []})})
    assert r.status_code == 422
    r = c.post("/api/jobs", files=[("files", ("a.pdf", b"%PDF-1.4", "application/pdf"))],
               data={"options": "{not json"})
    assert r.status_code == 422
    assert c.get("/api/jobs/doesnotexist").status_code == 404
    assert c.get("/api/jobs/abc/files/..%2F..%2Fsecret.txt").status_code == 404
    assert c.get("/api/jobs/../etc/files/x").status_code == 404
