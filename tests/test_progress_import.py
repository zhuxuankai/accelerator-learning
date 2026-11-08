import csv

from acc_cockpit.planning import import_legacy_progress


def test_legacy_import_is_explicit_and_never_confirms_completion(tmp_path):
    roadmap = tmp_path / "学习路线"
    roadmap.mkdir()
    legacy = roadmap / "进度追踪.csv"
    with legacy.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["类型", "名称", "关联课程", "计划完成", "状态", "来源", "更新日期", "备注"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "类型": "课程章节",
                "名称": "旧版已完成项",
                "关联课程": "课程一",
                "计划完成": "2026-01-01",
                "状态": "已完成",
                "来源": "已确认",
                "更新日期": "2026-01-01",
                "备注": "",
            }
        )

    preview = import_legacy_progress(tmp_path)
    assert preview["status"] == "dry_run"
    assert not (roadmap / "progress.csv").exists()
    imported = import_legacy_progress(tmp_path, accept=True)
    assert imported["status"] == "imported"
    rows = list(
        csv.DictReader((roadmap / "progress.csv").open("r", encoding="utf-8-sig", newline=""))
    )
    assert len(rows) == 1
    assert rows[0]["状态"] == "待确认"
    assert rows[0]["来源"] == "推断"
