# -*- coding: utf-8 -*-
"""生成单文件离线看板 dashboard.html（不依赖任何外部资源）。"""
from __future__ import annotations

import html

CSS = """
body{font-family:"Microsoft YaHei",system-ui,sans-serif;margin:24px;background:#f7f8fa;color:#1c1f23}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:28px 0 8px}
.sub{color:#6b7280;font-size:12px;margin-bottom:20px}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
th,td{border-bottom:1px solid #eceef1;padding:7px 10px;text-align:left;vertical-align:top}
th{background:#f1f3f6;font-weight:600}
.bar{background:#eceef1;height:8px;border-radius:4px;overflow:hidden;min-width:80px}
.bar span{display:block;height:8px;background:#3b82f6}
.badge{background:#fde68a;color:#7c5800;border-radius:4px;padding:0 6px;font-size:11px;margin-left:6px}
tr.ok td{background:#f2fbf4}
tr.doing td{background:#fffdf2}
.kpi{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px}
.kpi div{background:#fff;padding:12px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.06);min-width:120px}
.kpi b{display:block;font-size:20px}
.note{background:#fff;padding:12px 16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.06);font-size:13px}
"""


def _bar(value: int, scale: int) -> str:
    width = round(100 * value / scale) if scale else 0
    return '<div class="bar"><span style="width:' + str(width) + '%"></span></div>'


def render_dashboard(stats: dict, progress: list[dict], new_files: list[str], stamp: str) -> str:
    by_course = stats["by_course"]
    rows = []
    for course, info in sorted(by_course.items()):
        items = [r for r in progress if r.get("关联课程") == course]
        pct = 0
        if items:
            done = sum(1 for r in items if r.get("状态") == "已完成")
            pct = round(100 * done / len(items))
        rows.append((course, info))
    scale = max([info["chunks"] for _, info in rows] or [1])

    course_trs = []
    for course, info in rows:
        course_trs.append(
            "<tr><td>"
            + html.escape(course)
            + "</td><td>"
            + str(info["docs"])
            + "</td><td>"
            + str(info["latest_docs"])
            + "</td><td>"
            + str(info["units"])
            + "</td><td>"
            + str(info["chunks"])
            + "</td><td>"
            + str(info["ocr_units"])
            + "</td><td>"
            + _bar(info["chunks"], scale)
            + "</td></tr>"
        )

    doc_trs = []
    for doc in sorted(stats["docs"], key=lambda d: (d["course"], d["rel_path"])):
        flag = "" if doc["is_latest"] else '<span class="badge">旧版 v' + str(doc["version_rank"]) + "</span>"
        doc_trs.append(
            "<tr><td>"
            + html.escape(doc["course"])
            + "</td><td>"
            + html.escape(doc["rel_path"])
            + "</td><td>"
            + str(doc["n_units"])
            + "</td><td>"
            + str(doc["n_chunks"])
            + "</td><td>"
            + str(round(100 * (doc["ocr_ratio"] or 0))) + "%"
            + "</td><td>"
            + flag
            + "</td></tr>"
        )

    task_trs = []
    for row in progress:
        status = row.get("状态", "")
        cls = {"已完成": "ok", "进行中": "doing"}.get(status, "")
        badge = ' <span class="badge">待确认</span>' if row.get("来源") == "推断" else ""
        task_trs.append(
            '<tr class="'
            + cls
            + '"><td>'
            + html.escape(row.get("类型", ""))
            + "</td><td>"
            + html.escape(row.get("名称", ""))
            + "</td><td>"
            + html.escape(row.get("关联课程", ""))
            + "</td><td>"
            + html.escape(row.get("计划完成", ""))
            + "</td><td>"
            + html.escape(status)
            + "</td><td>"
            + html.escape(row.get("来源", ""))
            + badge
            + "</td></tr>"
        )

    total_docs = sum(i["docs"] for i in by_course.values())
    total_units = sum(i["units"] for i in by_course.values())
    total_ocr = sum(i["ocr_units"] for i in by_course.values())
    new_txt = "、".join(html.escape(x) for x in new_files) if new_files else "无"

    parts = [
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">",
        "<title>加速器学习驾驶舱</title><style>",
        CSS,
        "</style></head><body>",
        "<h1>加速器学习驾驶舱</h1>",
        '<div class="sub">生成时间 ' + html.escape(stamp) + "　·　语料仅含四门课目录与联网下载的论文</div>",
        '<div class="kpi">',
        "<div><b>" + str(total_docs) + "</b>文档</div>",
        "<div><b>" + str(total_units) + "</b>单元（页/张）</div>",
        "<div><b>" + str(stats["total_chunks"]) + "</b>索引块</div>",
        "<div><b>" + str(total_ocr) + "</b>OCR 单元</div>",
        "</div>",
        '<div class="note">本次新增/更新语料：' + new_txt + "</div>",
        "<h2>各目录覆盖</h2>",
        "<table><tr><th>目录</th><th>文档</th><th>最新版</th><th>单元</th><th>索引块</th><th>OCR 单元</th><th>相对规模</th></tr>",
        "".join(course_trs),
        "</table>",
        "<h2>档案明细</h2>",
        "<table><tr><th>目录</th><th>文件</th><th>单元</th><th>块</th><th>OCR 占比</th><th>版本</th></tr>",
        "".join(doc_trs),
        "</table>",
        "<h2>进度追踪</h2>",
        "<table><tr><th>类型</th><th>名称</th><th>关联课程</th><th>计划完成</th><th>状态</th><th>来源</th></tr>",
        "".join(task_trs) if task_trs else '<tr><td colspan="6">（暂无）</td></tr>',
        "</table>",
        "</body></html>",
    ]
    return "\n".join(parts)
