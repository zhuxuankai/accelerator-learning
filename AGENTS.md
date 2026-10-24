# 加速器学习驾驶舱 v2 · 工作区规则

## 语料边界

只读取 `kb/config.json` 的 `include_dirs` 和 `文献/`。不得引用工作区外目录，也不得把
`kb/`、`tools/`、`学习路线/`、`extensions/`、`examples/`、`tests/` 当作课程语料。

## 检索问答

1. 先运行 `pwsh tools/run.ps1 query "<问题>" -Mode hybrid`。
2. 只根据返回节点作答，并给出 `rel_path + unit_label`。
3. `diagnostics.warnings` 必须阅读。出现 `ambiguous` 时，不得声称某个版本一定最新；
   出现低质量 OCR 时，不得把 OCR 当公式原文。
4. `status: no_match` 时明确说明索引中没有匹配；依赖缺失或索引损坏不是 no-match，
   必须按非零错误报告修复命令。
5. 中文回答，专业术语保留英文，公式使用 LaTeX。

## 索引与版本

- 新语料：`pwsh tools/run.ps1 index`。
- 局部重建：`pwsh tools/run.ps1 index -Only "<相对路径>"`。
- 版本先后只按文件名中的显式日期/修订号；mtime 仅用于同日冲突并必须提示。
- 不要手工修改 `kb/v2/catalog.json` 或 `kb/v2/state.json`。

## 每周维护

运行 `pwsh tools/run.ps1 weekly`。它默认重建索引、执行可用评测、生成下周计划和看板。
汇报四件事：

1. 新增或变更语料；
2. 下周精读与泛读论文；
3. 当前阶段仿真任务；
4. “建议复习点”，而不是没有证据的“客观薄弱点”。

没有新语料、无逾期、无待确认事项时保持静默。评测集未人工审核或评测失败时必须明确说
“技术预览，未通过发布门槛”，不能宣称检索质量达标。

## 进度与阅读

- `progress.csv`、`reading.csv` 和 `roadmap.json` 是个人数据，不提交公开仓库。
- 来源为“推断”的记录不等于已完成。
- 只有 `progress confirm` 或 `reading confirm` 带证据时才能改成完成。
- 论文出现在计划中只表示“已安排”，不表示“已读”。

## 翻译扩展

翻译位于 `extensions/translation/`，不属于核心检索依赖。英文论文仍要求完整逐页中文译本；
完成前必须运行：

```powershell
pwsh extensions/translation/translation.ps1 -Audit
```

审计必须零缺页、零占位符、公式可渲染。OCR 低质量页和抽取残缺公式必须显式标页码，
不得猜测补全。

## 公开仓库

课程文件、论文、个人计划、进度、看板、译文、索引和 OCR 缓存不得提交。README 只描述
已实现且经过测试的能力；没有人工审核 held-out 集时不得发布检索指标结论。
