from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path


def _convert(args: argparse.Namespace) -> int:
    from ..application.dto import ConversionOptions, JobState, LatexMode
    from ..config import Settings
    from ..container import build_container
    from ..renderers.base import OutputFormat

    settings = Settings.from_env()
    if args.data_dir:
        object.__setattr__(settings, "data_dir", Path(args.data_dir).resolve())
    c = build_container(settings)
    opts = ConversionOptions(
        formats=[OutputFormat(f) for f in args.formats.split(",")],
        latex_mode=LatexMode(args.latex_mode),
        compile_latex=not args.no_compile,
        preview_docx=not args.no_preview,
        ocr=args.ocr,
        ocr_language=args.ocr_language,
        password=args.password,
        max_pages=args.max_pages,
    )
    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rc = 0
    for f in args.inputs:
        src = Path(f)
        job = c.jobs.run_sync(src.read_bytes(), src.name, opts)
        if job.state is not JobState.SUCCEEDED:
            print(f"[LỖI] {src.name}: {job.error}", file=sys.stderr)
            rc = 1
            continue
        job_dir = c.repo.job_dir(job.id)
        target = out_dir / job.stem
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(job_dir / "output", target)
        fid = {k: (round(sum(v) / len(v), 3) if v else None) for k, v in job.report.fidelity.items()}
        print(f"[OK] {src.name} -> {target}  ({job.report.timings.get('total')}s, độ giống {fid})")
        for w in job.report.warnings[:10]:
            print(f"     ! {w}")
        if args.json:
            print(json.dumps(job.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return rc


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from ..config import Settings

    s = Settings.from_env()
    uvicorn.run("pdfconv.presentation.api:create_app", factory=True,
                host=args.host or s.host, port=args.port or s.port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="pdfconv", description="Chuyển PDF sang LaTeX / DOCX")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sv = sub.add_parser("serve", help="Chạy giao diện web (mặc định http://127.0.0.1:8000)")
    sv.add_argument("--host")
    sv.add_argument("--port", type=int)
    sv.set_defaults(func=_serve)

    cv = sub.add_parser("convert", help="Chuyển đổi file từ dòng lệnh")
    cv.add_argument("inputs", nargs="+")
    cv.add_argument("-o", "--output", default="output")
    cv.add_argument("--formats", default="latex,docx")
    cv.add_argument("--latex-mode", choices=["exact", "flow"], default="exact")
    cv.add_argument("--no-compile", action="store_true")
    cv.add_argument("--no-preview", action="store_true")
    cv.add_argument("--ocr", action="store_true")
    cv.add_argument("--ocr-language", default="vie+eng")
    cv.add_argument("--password")
    cv.add_argument("--max-pages", type=int)
    cv.add_argument("--data-dir")
    cv.add_argument("--json", action="store_true")
    cv.set_defaults(func=_convert)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
