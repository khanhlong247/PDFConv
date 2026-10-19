from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import timedelta
from pathlib import Path

from ...application.dto import Job, utcnow


class JobRepository:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def job_dir(self, job_id: str) -> Path:
        if not job_id.isalnum():
            raise KeyError(job_id)
        return self.root / job_id

    def save(self, job: Job) -> None:
        with self._lock:
            d = self.job_dir(job.id)
            d.mkdir(parents=True, exist_ok=True)
            job.updated_at = utcnow()
            tmp = d / "job.json.tmp"
            tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(d / "job.json")

    def get(self, job_id: str) -> Job | None:
        try:
            p = self.job_dir(job_id) / "job.json"
        except KeyError:
            return None
        with self._lock:
            if not p.exists():
                return None
            return Job.model_validate(json.loads(p.read_text(encoding="utf-8")))

    def list(self, limit: int = 100) -> list[Job]:
        jobs = []
        for p in self.root.glob("*/job.json"):
            try:
                jobs.append(Job.model_validate(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def delete(self, job_id: str) -> bool:
        with self._lock:
            d = self.job_dir(job_id)
            if not d.exists():
                return False
            shutil.rmtree(d, ignore_errors=True)
            return True

    def resolve_file(self, job_id: str, rel: str) -> Path | None:
        base = self.job_dir(job_id).resolve()
        target = (base / rel).resolve()
        if base not in target.parents or not target.is_file():
            return None
        return target

    def purge_older_than(self, hours: int) -> int:
        cutoff = utcnow() - timedelta(hours=hours)
        n = 0
        for job in self.list(limit=10_000):
            if job.updated_at < cutoff and job.state in ("succeeded", "failed"):
                n += self.delete(job.id)
        return n
