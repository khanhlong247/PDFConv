from __future__ import annotations

from dataclasses import dataclass

from .application.job_service import JobService
from .application.pipeline import ConversionPipeline
from .config import Settings
from .infrastructure.pdf.ocr import OcrEngine
from .infrastructure.storage.job_store import JobRepository
from .infrastructure.toolchain.base import Toolchain
from .infrastructure.toolchain.local import LocalToolchain
from .infrastructure.toolchain.remote import CompositeToolchain, RemoteToolchain


@dataclass
class Container:
    settings: Settings
    toolchain: Toolchain
    ocr: OcrEngine
    repo: JobRepository
    pipeline: ConversionPipeline
    jobs: JobService


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    remote = RemoteToolchain(settings.toolchain_url, settings.toolchain_timeout) if settings.toolchain_url else None
    toolchain = CompositeToolchain(LocalToolchain(enable_word=settings.enable_word), remote)
    ocr = OcrEngine()
    repo = JobRepository(settings.data_dir)
    pipeline = ConversionPipeline(settings, toolchain, ocr)
    jobs = JobService(repo, pipeline, settings.workers)
    return Container(settings, toolchain, ocr, repo, pipeline, jobs)
