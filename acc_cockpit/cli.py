from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from .config import CockpitError, Paths, load_config, workspace_root
from .evaluation import evaluate
from .indexer import build_index
from .planning import (
    confirm_progress,
    confirm_reading,
    generate_weekly,
    list_progress,
    list_reading,
    reject_progress,
    suggest_progress,
)
from .retrieval import query


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def doctor(root: Path) -> dict:
    cfg, config_file, using_example = load_config(root)
    paths = Paths.for_root(root)
    checks = {
        "python": sys.version.split()[0],
        "config": str(config_file),
        "using_example_config": using_example,
        "index_state": paths.state_file.exists(),
        "catalog": paths.catalog_file.exists(),
        "chroma": paths.chroma_dir.exists(),
        "pymupdf": _module("fitz"),
        "python_pptx": _module("pptx"),
        "python_docx": _module("docx"),
        "llama_index": _module("llama_index"),
        "chromadb": _module("chromadb"),
        "sentence_transformers": _module("sentence_transformers"),
        "rapidocr": _module("rapidocr_onnxruntime"),
    }
    missing = []
    for name in ("pymupdf", "llama_index", "chromadb", "sentence_transformers"):
        if not checks[name]:
            missing.append(name)
    actions = []
    if missing:
        actions.append("安装核心依赖：python -m pip install -e .")
    if not checks["rapidocr"]:
        actions.append("需要扫描件 OCR 时安装：python -m pip install -e .[ocr]")
    if not paths.state_file.exists():
        actions.append("建立索引：run.ps1 index")
    return {
        "status": "ok" if not missing else "missing_dependencies",
        "checks": checks,
        "include_dirs": cfg.get("include_dirs"),
        "actions": actions,
    }


def status(root: Path) -> dict:
    cfg, config_file, using_example = load_config(root)
    paths = Paths.for_root(root)
    state = {}
    if paths.state_file.exists():
        try:
            state = json.loads(paths.state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {"corrupt": True}
    progress = list_progress(root)
    reading = list_reading(root)
    return {
        "status": "ok" if state and not state.get("corrupt") else "index_missing_or_corrupt",
        "config": str(config_file),
        "using_example_config": using_example,
        "include_dirs": cfg.get("include_dirs"),
        "index": {
            "files": len(state.get("files", {})),
            "nodes": state.get("node_count", 0),
            "semantic_nodes": state.get("semantic_node_count", 0),
            "built_at": state.get("built_at"),
            "warnings": [
                warning
                for warning in state.get("warnings", [])
                if "歧义" in warning or "多个文件" in warning
            ],
        },
        "progress_items": len(progress),
        "reading_items": len(reading),
    }


def papers(root: Path, *, dry_run: bool) -> int:
    script = root / "tools" / "fetch_papers.py"
    if not script.exists():
        raise CockpitError("找不到 tools/fetch_papers.py。")
    command = [sys.executable, str(script)]
    if not dry_run:
        command.append("--write")
    return subprocess.call(command, cwd=root)


def _common_index(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--only")
    parser.add_argument("--mock-embedding", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acc-cockpit")
    parser.add_argument("--workspace", help="工作区根目录；默认自动推导")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")
    index_parser = sub.add_parser("index")
    _common_index(index_parser)

    query_parser = sub.add_parser("query")
    query_parser.add_argument("text")
    query_parser.add_argument("--course")
    query_parser.add_argument("--kind", choices=["slide", "book", "paper", "doc"])
    query_parser.add_argument("-k", "--top-k", type=int, default=8)
    query_parser.add_argument("--all-versions", action="store_true")
    query_parser.add_argument("--mode", choices=["lexical", "vector", "hybrid"], default="hybrid")
    query_parser.add_argument("--mock-embedding", action="store_true")

    eval_parser = sub.add_parser("eval")
    eval_parser.add_argument("--suite", choices=["demo", "local"], default="demo")
    eval_parser.add_argument("--split", choices=["dev", "heldout"], default="dev")
    eval_parser.add_argument("--baseline", choices=["lexical", "vector", "hybrid"], default="hybrid")
    eval_parser.add_argument("--mock-embedding", action="store_true")

    weekly_parser = sub.add_parser("weekly")
    weekly_parser.add_argument("--no-index", action="store_true")
    weekly_parser.add_argument("--skip-eval", action="store_true")
    weekly_parser.add_argument("--mock-embedding", action="store_true")

    progress_parser = sub.add_parser("progress")
    progress_sub = progress_parser.add_subparsers(dest="progress_command", required=True)
    progress_sub.add_parser("list")
    suggest_parser = progress_sub.add_parser("suggest")
    suggest_parser.add_argument("--accept", action="store_true")
    confirm_parser = progress_sub.add_parser("confirm")
    confirm_parser.add_argument("id")
    confirm_parser.add_argument("--evidence", required=True)
    reject_parser = progress_sub.add_parser("reject")
    reject_parser.add_argument("id")

    reading_parser = sub.add_parser("reading")
    reading_sub = reading_parser.add_subparsers(dest="reading_command", required=True)
    reading_sub.add_parser("list")
    reading_confirm = reading_sub.add_parser("confirm")
    reading_confirm.add_argument("id")
    reading_confirm.add_argument("--evidence", required=True)

    papers_parser = sub.add_parser("papers")
    papers_parser.add_argument("--dry-run", action="store_true")
    papers_parser.add_argument("--write", action="store_true")
    sub.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = workspace_root(args.workspace)
    try:
        if args.command == "doctor":
            result = doctor(root)
            _print(result)
            return 0 if result["status"] == "ok" else 2
        if args.command == "status":
            result = status(root)
            _print(result)
            return 0 if result["status"] == "ok" else 2
        if args.command == "index":
            _print(
                build_index(
                    root,
                    full=args.full,
                    only=args.only,
                    mock_embedding=args.mock_embedding,
                )
            )
            return 0
        if args.command == "query":
            result = query(
                root,
                args.text,
                course=args.course,
                kind=args.kind,
                top_k=args.top_k,
                all_versions=args.all_versions,
                mode=args.mode,
                mock_embedding=args.mock_embedding,
            )
            _print(result)
            return 0
        if args.command == "eval":
            _print(
                evaluate(
                    root,
                    suite=args.suite,
                    baseline=args.baseline,
                    mock_embedding=args.mock_embedding,
                    split=args.split,
                )
            )
            return 0
        if args.command == "weekly":
            index_result = None
            if not args.no_index:
                index_result = build_index(root, mock_embedding=args.mock_embedding)
            eval_result = None
            eval_error = None
            if not args.skip_eval:
                try:
                    eval_result = evaluate(
                        root,
                        suite="local",
                        baseline="hybrid",
                        mock_embedding=args.mock_embedding,
                    )
                except CockpitError as exc:
                    eval_error = str(exc)
            plan = generate_weekly(root, eval_result=eval_result)
            plan["index"] = index_result
            plan["eval_error"] = eval_error
            _print(plan)
            eval_required = load_config(root)[0].get("weekly", {}).get("eval_required", True)
            return 1 if eval_error and eval_required else 0
        if args.command == "progress":
            if args.progress_command == "list":
                _print(list_progress(root))
            elif args.progress_command == "suggest":
                _print(suggest_progress(root, accept=args.accept))
            elif args.progress_command == "confirm":
                _print(confirm_progress(root, args.id, args.evidence))
            else:
                _print(reject_progress(root, args.id))
            return 0
        if args.command == "reading":
            if args.reading_command == "list":
                _print(list_reading(root))
            else:
                _print(confirm_reading(root, args.id, args.evidence))
            return 0
        if args.command == "papers":
            return papers(root, dry_run=not args.write)
        raise CockpitError(f"未知命令：{args.command}")
    except CockpitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
