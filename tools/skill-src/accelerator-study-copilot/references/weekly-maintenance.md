# 每周维护

## 调用

在工作区根目录运行：

```powershell
pwsh tools/run.ps1 weekly
```

新增课件后会增量入库、更新索引和看板、运行配置的评测套件并生成下周计划。不要为了查看本周任务反复运行 weekly；已存在计划时直接读取 `学习路线/plans/`。

## 解释状态

- `status=ok`：索引、计划和评测均成功。
- `status=degraded`：索引和计划成功，但人工审核评测集不可用或模型/评测前置条件不足。必须说明“技术预览，未通过质量门槛”，不要把它说成质量通过。
- `status=failed`：已审核评测集未达到阈值，或索引/计划生成失败。报告失败项和修复路径，不继续宣称完成。

返回摘要中的 `corpus`、`papers`、`simulation`、`review_candidates`、`quality` 和 `artifacts` 是主要依据。 `eval_error` 只作为诊断，不应替代整体 `status`。

## 汇报

1. 新增、更新或移除的语料。
2. 下周 1 篇精读与 1 篇泛读及选择类别。
3. 当前阶段下一项仿真任务。
4. 有进度证据的“建议复习点”；没有 `progress.csv` 或证据不足时写“无法判断”。

论文出现在计划中只表示已安排。当前精读论文若已有中文译本，报告页数和状态；翻译未完成时转读
[translation-and-math.md](translation-and-math.md)。

交互请求中直接汇报结果。 heartbeat 请求只有在本周有新变化、逾期、失败或需要用户确认时通知。
