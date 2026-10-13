# 学习驾驶舱 · 工作区规则

这个工作区是"知识库 + 学习路线"的组合体。任何会话（包括以后开的）都应遵守下面几条。

## 语料边界（硬约束）

知识库只索引两类材料，不读、不引用任何其它目录：

1. 工作区里的课程目录：`kb/config.json` 的 `include_dirs` 列出的那几个；
2. 联网下载的论文：`文献/`。

明确不用：工作区以外的任何目录，以及本工作区的 `kb/`、`tools/`、`学习路线/`（这些是产物，不是语料）。

## 回答课程问题时的固定动作

1. 先检索：`pwsh tools/run.ps1 query "<问题>"`（可加 `-Course` 限定目录、`-K` 调条数）。
2. 基于返回的片段作答，并给出处：`文件名 + 页/张`（例如 `<课程目录>/<讲义文件>.pdf 页12`）。
3. 检索不到就直说课件里没有，然后按物理常识讲解，并明确标注这是常识讲解、不是课件内容。
4. 公式：扫描版课件的公式在 OCR 里是乱码，不要假装引用原文，直接讲原理。
5. 中文回答，专业术语保留英文。

## 维护动作

- 有新课件：把文件丢进对应课程目录，然后 `pwsh tools/run.ps1 ingest`（增量入库）。
- 每周维护：`pwsh tools/run.ps1 weekly`，刷新 `学习路线/覆盖度.md`、`学习路线/dashboard.html` 和下一周计划。
- 论文语料：`pwsh tools/run.ps1 papers`（先看候选清单，确认后加 `-Write` 下载）。
- 查状态：`pwsh tools/run.ps1 status`；检索回归：`pwsh tools/run.ps1 eval 3`。

## 进度回填纪律

`学习路线/进度追踪.csv` 的每一行都带 `来源` 字段：

- `已确认`：用户明确说过，或以作业/代码/产出为证；
- `推断`：系统根据课件、对话推测的。

**绝不擅自把 `推断` 改成已完成**。每周维护时只把 `推断` 项列成待确认清单交给用户。

## 个人数据边界

`kb/config.json`、`kb/papers/`、`学习路线/学习路线.md`、`进度追踪.csv`、`覆盖度.md`、
`dashboard.html`、`周计划/` 属于个人数据，已在 `.gitignore` 中排除，**不要**把它们提交到
公开仓库；需要对外分享时只提供同目录的 `*.example.*` 模板。

## 复用的既有 skill

- 文献综述/检索综述 → `deep-research`
- 笔记、报告、论文写作 → `academic-paper`
- 审稿式自查 → `academic-paper-reviewer`
- 端到端"研究→写作→评审" → `academic-pipeline`
- 组会幻灯片 → `ppt-master-skill`

## 环境注意

一律通过 `tools/run.ps1` 调用脚本；它内部按"`ACCKB_*` 环境变量 → Codex 自带运行时 → 系统 PATH"
的顺序自动探测 Python / Node / Poppler，换机器不用改代码。

## 配套件

- 个人技能 `accelerator-study-copilot` 装在 `$CODEX_HOME/skills/`（默认 `~/.codex/skills/`）下；
  源码副本在 `tools/skill-src/accelerator-study-copilot/`。
- 每周五 21:00 有一条 heartbeat 自动化「每周学习路线维护」，动作就是本文件里的"每周维护"。
- 看板：`学习路线/dashboard.html`（单文件、离线可开）；覆盖度：`学习路线/覆盖度.md`。
