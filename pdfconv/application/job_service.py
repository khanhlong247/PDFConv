from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from ..domain.errors import ConversionError
from ..infrastructure.storage.job_store import JobRepository
from ..infrastructure.pdf.input import safe_stem
from .dto import ConversionOptions, Job, JobState
from .pipeline import ConversionPipeline

log = logging.getLogger(__name__)


class JobService:
    def __init__(self, repo: JobRepository, pipeline: ConversionPipeline, workers: int = 1):
        self.repo = repo
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="pdfconv")
        self._lock = threading.Lock()
        self._mupdf_lock = threading.Lock()
        self._recover()

    def _recover(self) -> None:
        for job in self.repo.list(limit=10_000):
            if job.state in (JobState.QUEUED, JobState.RUNNING):
                job.state = JobState.FAILED
                job.error = "Máy chủ đã khởi động lại khi job đang chạy."
                job.message = "Bị gián đoạn"
                self.repo.save(job)

    def submit(self, data: bytes, filename: str, options: ConversionOptions) -> Job:
        job = Job(id=self.repo.new_id(), filename=filename or "document.pdf",
                  stem=safe_stem(filename), options=options.public())
        self.repo.save(job)
        self.executor.submit(self._run, job.id, data, options)
        return job

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self.repo.get(job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            self.repo.save(job)

    def _run(self, job_id: str, data: bytes, options: ConversionOptions) -> None:
        job = self.repo.get(job_id)
        if job is None:
            return
        self._update(job_id, state=JobState.RUNNING, progress=1, message="Bắt đầu")

        def progress(p: int, msg: str) -> None:
            self._update(job_id, progress=p, message=msg)

        try:
            with self._mupdf_lock:
                artifacts, report = self.pipeline.run(self.repo.job_dir(job_id), data, job.filename,
                                                      options, progress)
            self._update(job_id, state=JobState.SUCCEEDED, progress=100, message="Hoàn tất",
                         artifacts=artifacts, report=report)
        except ConversionError as exc:
            self._update(job_id, state=JobState.FAILED, message="Thất bại", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            log.error("Job %s lỗi:\n%s", job_id, traceback.format_exc())
            self._update(job_id, state=JobState.FAILED, message="Lỗi hệ thống",
                         error=f"{type(exc).__name__}: {exc}")

    def run_sync(self, data: bytes, filename: str, options: ConversionOptions) -> Job:
        job = Job(id=self.repo.new_id(), filename=filename, stem=safe_stem(filename),
                  options=options.public())
        self.repo.save(job)
        self._run(job.id, data, options)
        return self.repo.get(job.id)

    def get(self, job_id: str) -> Job | None:
        return self.repo.get(job_id)

    def list(self) -> list[Job]:
        return self.repo.list()

    def delete(self, job_id: str) -> bool:
        return self.repo.delete(job_id)
