import csv
import json
from pathlib import Path

import pytest

from acc_cockpit.config import CockpitError
from acc_cockpit.planning import confirm_progress, generate_weekly


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_inferred_item_requires_explicit_confirmation(tmp_path):
    rows = [
        {
            "id": "p1",
            "类型": "课程章节",
            "名称": "beta 函数",
            "关联课程": "course-a",
            "计划完成": "",
            "状态": "进行中",
            "来源": "推断",
            "证据": "无",
            "更新日期": "2026-10-24",
            "备注": "",
        }
    ]
    _write_csv(tmp_path / "学习路线" / "progress.csv", rows)
    with pytest.raises(CockpitError):
        confirm_progress(tmp_path, "p1", "")
    result = confirm_progress(tmp_path, "p1", "完成作业并提交")
    assert result["状态"] == "已完成"
    assert result["来源"] == "已确认"


def test_weekly_plan_has_no_placeholders(tmp_path):
    (tmp_path / "学习路线").mkdir(parents=True)
    (tmp_path / "学习路线" / "roadmap.json").write_text(
        json.dumps(
            {
                "stages": [
                    {
                        "id": "s",
                        "name": "阶段",
                        "start": "2026-01-01",
                        "end": "2027-12-31",
                        "simulation_tasks": [
                            {"title": "完成 FODO 匹配", "instructions": "输出 beta 与色散曲线"}
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "kb").mkdir(parents=True)
    (tmp_path / "kb" / "config.json").write_text(
        json.dumps({"version": 2, "include_dirs": ["文献"]}),
        encoding="utf-8",
    )
    result = generate_weekly(tmp_path, eval_result=None)
    markdown = Path(tmp_path / result["plan"]).read_text(encoding="utf-8")
    second = generate_weekly(tmp_path, eval_result=None)
    assert second["generated_at"] == result["generated_at"]
    assert "待填" not in markdown
    assert "按阶段填写" not in markdown
    assert "无法判断" in markdown
