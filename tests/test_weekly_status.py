import json

from acc_cockpit import cli
from acc_cockpit.config import CockpitError


def _workspace(tmp_path):
    (tmp_path / "kb").mkdir()
    (tmp_path / "kb" / "config.json").write_text(
        json.dumps(
            {
                "include_dirs": ["文献"],
                "weekly": {"eval_suite": "local", "eval_required": True},
            }
        ),
        encoding="utf-8",
    )


def _fake_plan(root, **kwargs):
    return {
        "week": "2026-11-09",
        "papers": [],
        "simulation": None,
        "reviews": [],
        "eval": kwargs.get("eval_result"),
        "plan": "学习路线/plans/2026-11-09.md",
        "dashboard": "学习路线/dashboard.html",
    }


def test_weekly_missing_eval_is_degraded_success(tmp_path, monkeypatch, capsys):
    _workspace(tmp_path)
    monkeypatch.setattr(cli, "build_index", lambda *args, **kwargs: {"indexed_files": 1})
    monkeypatch.setattr(
        cli,
        "evaluate",
        lambda *args, **kwargs: (_ for _ in ()).throw(CockpitError("评测不可用")),
    )
    monkeypatch.setattr(cli, "generate_weekly", _fake_plan)
    assert cli.main(["--workspace", str(tmp_path), "weekly", "--mock-embedding"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "degraded"
    assert payload["quality"]["status"] == "unavailable"


def test_weekly_approved_eval_below_threshold_fails(tmp_path, monkeypatch, capsys):
    _workspace(tmp_path)
    monkeypatch.setattr(cli, "build_index", lambda *args, **kwargs: {"indexed_files": 1})
    monkeypatch.setattr(
        cli,
        "evaluate",
        lambda *args, **kwargs: {
            "suite": "local",
            "split": "dev",
            "baseline": "hybrid",
            "page_hit@3": 0.4,
            "recall@50": 0.6,
            "empty_rate": 0.2,
        },
    )
    monkeypatch.setattr(cli, "generate_weekly", _fake_plan)
    assert cli.main(["--workspace", str(tmp_path), "weekly", "--mock-embedding"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
