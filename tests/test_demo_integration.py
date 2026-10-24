import json
import shutil
from pathlib import Path

from acc_cockpit.evaluation import evaluate
from acc_cockpit.indexer import build_index
from acc_cockpit.retrieval import query

REPO = Path(__file__).resolve().parents[1]


def _demo_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "kb").mkdir(parents=True)
    shutil.copytree(REPO / "examples" / "demo-corpus" / "course-a", root / "course-a")
    shutil.copytree(REPO / "examples" / "demo-corpus" / "course-b", root / "course-b")
    shutil.copytree(REPO / "examples" / "demo-corpus" / "文献", root / "文献")
    shutil.copytree(REPO / "kb" / "eval" / "v2", root / "kb" / "eval" / "v2")
    config = {
        "version": 2,
        "include_dirs": ["course-a", "course-b", "文献"],
        "exclude": ["kb", "学习路线", "extensions", "examples", "tests"],
        "index": {"embedding_model": "intfloat/multilingual-e5-small"},
    }
    (root / "kb" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def test_demo_end_to_end_with_mock_embedding(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    root = _demo_workspace(tmp_path)
    index = build_index(root, mock_embedding=True)
    assert index["indexed_files"] == 4
    response = query(root, "FODO cell 匹配要检查什么", mode="hybrid", mock_embedding=True, top_k=5)
    assert response["status"] == "ok"
    assert any(
        item["rel_path"] == "course-a/横向动力学-0923.md"
        for item in response["results"]
    )
    all_versions = query(
        root,
        "横向动力学 0922",
        mode="hybrid",
        all_versions=True,
        mock_embedding=True,
        top_k=10,
    )
    paths = {item["rel_path"] for item in all_versions["results"]}
    assert "course-a/横向动力学-0922.md" in paths
    assert "course-a/横向动力学-0923.md" in paths
    no_match = query(root, "zzzz-unfindable-token", mode="lexical")
    assert no_match["status"] == "no_match"
    assert no_match["results"] == []
    metrics = evaluate(
        root,
        suite="demo",
        split="heldout",
        baseline="hybrid",
        mock_embedding=True,
    )
    assert metrics["empty_rate"] == 0
    assert metrics["page_hit@3"] >= 0.66
    partial = build_index(
        root,
        only="course-b/束流诊断.md",
        mock_embedding=True,
    )
    assert partial["indexed_files"] == 4
