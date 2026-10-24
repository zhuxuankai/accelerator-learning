import json

from acc_cockpit.cli import main


def test_query_missing_index_is_nonzero_and_actionable(tmp_path, capsys):
    (tmp_path / "kb").mkdir()
    (tmp_path / "kb" / "config.json").write_text(
        json.dumps({"version": 2, "include_dirs": ["文献"]}),
        encoding="utf-8",
    )
    code = main(["--workspace", str(tmp_path), "query", "测试问题"])
    captured = capsys.readouterr()
    assert code == 2
    assert "v2 索引不存在" in captured.err
    assert "run.ps1 index" in captured.err
