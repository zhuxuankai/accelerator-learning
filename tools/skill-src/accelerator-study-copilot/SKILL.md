---
name: accelerator-study-copilot
description: 在加速器学习驾驶舱工作区中检索课程与论文、维护学习路线、确认进度和阅读状态，并管理论文中文译本校对。适用于带页/张出处的课程问答、周计划、文献选择、知识库维护和公式渲染排障；不用于工作区外的一般编程或写作。
metadata:
  short-description: 加速器课程检索、学习规划与译本校对
---

# 加速器学习驾驶舱

工作区根目录以包含 `kb/config.json` 和 `tools/run.ps1` 的目录为准。只读取
`include_dirs` 列出的课程目录和 `文献/`；索引、计划、脚本、演示和测试文件都不是课程语料。

## 先判断任务

- **概念解释、跨中英文问法、找相关课件**：读
  [references/retrieval-and-citations.md](references/retrieval-and-citations.md)，用 hybrid 检索。
- **明确文件名、缩写、公式号、术语或原文片段**：用 lexical 检索；具体判据见同一 reference。
- **“本周任务是什么”**：只读取现有 `学习路线/plans/` 或 `dashboard.html`，不要重建索引。
- **“下周学什么”、每周维护、补充新课件**：读
  [references/weekly-maintenance.md](references/weekly-maintenance.md)。
- **“我读完了”“这项做完了”“进度如何”**：读
  [references/progress-and-reading.md](references/progress-and-reading.md)。
- **翻译、逐页覆盖、公式标红或 Markdown+Math 渲染问题**：读
  [references/translation-and-math.md](references/translation-and-math.md)。

## 不可违反的结果规则

1. 课程结论必须来自本次检索结果，并给出 `rel_path + unit_label`。
2. 必须检查 `diagnostics.warnings`。版本歧义不得自行宣布最新；低质量 OCR 只能用于定位，
   不能作为公式原文。
3. `no_match`、索引缺失、依赖损坏和网络失败必须区分。错误不能伪装成“课件里没有”。
4. 计划出现、文件存在、筛选结果或“推断”来源都不等于已完成或已读。
5. 完成状态只能通过带证据的 `progress confirm` 或 `reading confirm` 修改。
6. `weekly` 的 degraded 只表示维护完成但质量门槛不可用；不得称为质量通过。
7. 不手工修改索引状态、catalog 或个人进度 CSV。

## 输出方式

- 工具返回 JSON 时，提炼结论和出处，不倾倒整段 JSON。
- 公式使用工作区已验证的 Markdown+Math 语法；与渲染问题有关的任务先读
  [translation-and-math reference](references/translation-and-math.md)。
- 任务受阻时给一条可执行的修复命令或一个明确的用户确认项，不发散猜测。
