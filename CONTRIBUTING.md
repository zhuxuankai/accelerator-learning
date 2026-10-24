# 贡献指南

本项目是个人本地工具，欢迎可复现的 bug 报告和范围明确的 PR。

## 提交前检查

```powershell
.\.venv\Scripts\python -m ruff check acc_cockpit tests extensions/translation
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m acc_cockpit.cli --workspace <demo-root> index --mock-embedding
```

涉及检索排序的 PR 必须同时报告 lexical、vector、hybrid 三种基线在 demo held-out 上的
page hit@3、Recall@50、MRR@10、nDCG@10、空结果率和 p95 延迟。只有 demo 结果不能证明真实
课程语料质量。

## 代码约定

- Python 3.10+，格式与 lint 由 `ruff` 管理。
- LlamaIndex 管理节点和检索，Chroma 持久化向量；不要恢复手写“伪 RAG”评分权重。
- 查询结果必须保留精确 `rel_path` 和 `unit_label`。
- 版本判断不得以 mtime 作为首选依据。
- OCR 缓存必须幂等，低质量页不得进入语义索引。
- 缺失索引和依赖错误必须非零退出，禁止静默返回空结果。
- 计划生成不得出现“待填”“按阶段填写”等占位任务。
- 推断状态不能自动变成完成。

## 不要提交

- 课程讲义、教材和论文 PDF；
- 个人 `progress.csv`、`reading.csv`、`roadmap.json`、计划和看板；
- `kb/v2/`、`kb/legacy/` 或任何向量数据库；
- 私人译文和 OCR 文本。

只使用合成 demo 或可公开授权的样例作为测试数据。
