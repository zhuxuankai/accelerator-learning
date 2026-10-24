---
name: accelerator-study-copilot
description: 在加速器学习驾驶舱 v2 中做带精确页/张出处的混合检索问答、每周学习规划、进度确认和知识库维护。适用于课程问题、论文安排、仿真任务、索引与学习路线维护；不用于工作区外的通用写作或编程。
metadata:
  short-description: 加速器课程混合检索与可信学习规划
---

# 加速器学习驾驶舱 v2

工作区根目录以 clone 位置为准。只读取 `kb/config.json` 的 `include_dirs` 和 `文献/`；
不要引用工作区外目录，也不要把索引、计划、脚本或演示数据当作课程语料。

## 命令

- `run.ps1 doctor`
- `run.ps1 index [-Full] [-Only <path>]`
- `run.ps1 query "<问题>" [-Course X] [-Kind slide|book|paper|doc] [-K 8] [-AllVersions] [-Mode hybrid]`
- `run.ps1 eval -Suite local -Split dev -Baseline hybrid`
- `run.ps1 weekly`
- `run.ps1 progress list|suggest|confirm|reject`
- `run.ps1 reading list|confirm`
- `run.ps1 status`

## 检索问答

1. 先运行混合检索，不要凭记忆引用课件。
2. 回答必须给出 `rel_path + unit_label`。
3. 阅读 `diagnostics.warnings`。版本歧义不得擅自选一个；低质量 OCR 只能用于定位，
   不能当公式原文。
4. `no_match`、依赖缺失和索引损坏要区分。后者必须报告非零错误及修复命令。
5. 检索结果不足时指出下一张/页，不堆砌无关片段。

## 每周维护

运行 `run.ps1 weekly`，汇报：

1. 新增或变更语料；
2. 下周精读和泛读论文；
3. 当前阶段仿真任务；
4. 有证据支持的“建议复习点”。

没有变化、逾期或待确认事项时保持静默。评测必须使用人工审核的 local held-out 集才能声明
质量；未审核或失败时只能称技术预览。

## 进度纪律

- 计划中出现论文不等于已读。
- `来源=推断` 不等于完成。
- 只有带证据的 `progress confirm` 或 `reading confirm` 才能标记完成。
- 不手工把推断项改成已完成。

## 翻译扩展

翻译是可选扩展，位于 `extensions/translation/`。交付英文论文中文译本前必须运行：

```powershell
pwsh extensions/translation/translation.ps1 -Audit
```

审计必须零缺页、零占位符、公式可渲染。低质量 OCR 或抽取残缺公式要标页码，不得猜补。
