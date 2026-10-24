# 加速器学习驾驶舱 v2

一个本地优先的个人学习工具：把课程讲义和论文解析成带精确页码的节点，用
LlamaIndex + Chroma + multilingual-e5-small 做词法与向量混合检索，并根据明确记录的
学习进度生成每周计划。

它面向单个研究者维护自己的课程与文献，不承诺零配置、零依赖或开箱即用的公共知识库。
课程文件、论文、个人进度和译文都留在本机，不进入 Git。

## v2 的核心边界

- 检索是真实的混合检索：BM25 词法召回 + E5 向量召回，使用 reciprocal-rank fusion 合并。
- 每个结果返回文件、页码/张号、课程和版本依据；低质量 OCR 不会进入向量索引。
- 文件名中的日期或修订号决定版本先后，mtime 只在同一显式版本的冲突中作为有警告的次级判断。
- 论文出现在计划里不等于已读；只有带证据的阅读确认才改变阅读状态。
- 推断的课程进度不能被直接改成已完成。
- 每周计划从结构化 `roadmap.json`、`progress.csv` 和 `reading.csv` 生成，不使用占位任务。
- 翻译是可选扩展，不属于核心检索依赖。

## 安装

需要 Python 3.10+。推荐在仓库根目录创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
```

扫描版课件额外安装 OCR：

```powershell
.\.venv\Scripts\python -m pip install -e ".[ocr]"
```

首次建立向量索引时会下载默认模型 `intfloat/multilingual-e5-small`。模型和索引均为本地文件。

配置按以下顺序读取：

1. `ACCKB_WORKSPACE` 指定的工作区；
2. `kb/config.json`；
3. `kb/config.example.json`。

新工作区应从模板创建配置，并把 `include_dirs` 改成真实课程目录：

```powershell
Copy-Item kb/config.example.json kb/config.json
Copy-Item 学习路线/roadmap.example.json 学习路线/roadmap.json
```

## 命令

```powershell
.\tools\run.ps1 doctor
.\tools\run.ps1 index
.\tools\run.ps1 query "BPM 怎么测横向位置" -K 5
.\tools\run.ps1 query "色散函数" -Mode hybrid -AllVersions
.\tools\run.ps1 eval -Suite demo -Split dev -Baseline hybrid
.\tools\run.ps1 weekly
.\tools\run.ps1 progress list
.\tools\run.ps1 progress suggest
.\tools\run.ps1 progress confirm prog-xxxx --evidence "完成并提交作业"
.\tools\run.ps1 reading list
.\tools\run.ps1 reading confirm paper-xxxx --evidence "读书笔记已归档"
.\tools\run.ps1 papers -DryRun
.\tools\run.ps1 status
```

`query` 输出一个 JSON 对象：

```json
{
  "status": "ok",
  "results": [
    {
      "rel_path": "课程/讲义.pdf",
      "unit_label": "页12",
      "vector_rank": 2,
      "lexical_rank": 1,
      "fused_score": 0.0325,
      "version_basis": "filename_date"
    }
  ],
  "diagnostics": {
    "warnings": [],
    "errors": []
  }
}
```

没有索引、配置损坏或依赖缺失会返回非零退出码和修复命令。只有索引正常但确实没有匹配时，
才返回 `status: no_match`。

## 版本与 OCR

支持的显式版本标记包括文件名末尾的 `0923`、`20260923`、`v2`、`第2版` 和数字修订号。
无法判断先后的多个文件不会互相遮蔽：它们都会保留在检索范围内，并产生 `ambiguous` 警告。

OCR 缓存位于 `kb/v2/ocr.sqlite`，主键为：

```text
(file_sha1, page, dpi, language, model_version)
```

同一页重复 OCR 会 upsert，不会追加重复记录。OCR 页记录置信度、替换字符比例和噪声比例；
低质量页保留供定位，但不进入语义向量索引。

Chroma 的 HNSW 向量库不放在 OneDrive 同步目录中，而是放在
`%LOCALAPPDATA%\accelerator-learning-cockpit\<workspace-id>\chroma`。正文 catalog 与状态
仍位于 `kb/v2/`；删除本机缓存后可从 catalog 和语料重建向量库。

## 学习计划数据

以下文件属于个人数据，已被 `.gitignore` 排除：

- `学习路线/roadmap.json`：阶段、日期和仿真任务；
- `学习路线/progress.csv`：课程、仿真和写作进度；
- `学习路线/reading.csv`：论文阅读状态；
- `学习路线/plans/`：每周计划及结构化状态；
- `学习路线/dashboard.html`：离线看板。

`progress suggest` 只会生成来源为“推断”的候选；必须显式接受后才写入正式进度。
`progress confirm` 和 `reading confirm` 必须提供证据。

## 评测

当前仓库自带合成 demo 语料和人工设计的 demo dev/held-out 集，用于 CI 与安装检查。
个人课程语料的质量评测要求使用 `kb/eval/v2/local-dev.jsonl` 和
`kb/eval/v2/local-heldout.jsonl`，每题包含精确文件、页码和答案支撑片段，并由用户审核
`approved: true`。

指标包括 page hit@3、Recall@50、MRR@10、nDCG@10、空结果率和延迟。旧版按“文件名出现”
判定的 20 题只保留为 smoke 数据，不再作为检索质量证明。

## 翻译扩展

翻译工具移到 `extensions/translation/`：

```powershell
.\extensions\translation\translation.ps1 -List
.\extensions\translation\translation.ps1 -Prepare "文献/example.pdf"
.\extensions\translation\translation.ps1 -Audit
```

它单独安装依赖：

```powershell
.\.venv\Scripts\python -m pip install -e ".[translation]"
```

## 已知限制

- E5 模型主要解决跨中英文表达差异，不等同于领域推理；最终回答仍需核对原始页面。
- 公式和复杂表格仍可能抽取不完整。低质量 OCR 只用于定位，不应被当作公式原文。
- DOCX 没有稳定的固定页码，定位到“正文”。
- 论文自动抓取仍依赖外部开放 API，详细候选必须人工确认后再下载。
- 人工审核的本地 held-out 集完成前，本项目只能声明为技术预览，不能声明达到特定检索指标。

## 贡献

欢迎提交 issue 和 PR。新增功能必须同时提供测试和真实的行为说明。请不要提交课程 PDF、
论文、个人进度或私人译文。许可证见 [LICENSE](LICENSE)。
