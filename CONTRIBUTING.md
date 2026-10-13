# 贡献指南

欢迎提 issue 和 pull request。这是个个人学习项目的工具层，目标很简单：**让"课程材料 + 论文"
变成可检索、可追责的知识库，并自动维护一份学习路线**。

## 提 issue

先说清楚三件事，我处理起来会快很多：

1. 你跑的是哪条命令（`run.ps1` 的子命令与参数）；
2. 期望结果与实际结果；
3. 报错原文（脚本会把 `[error]` 行打到终端，OCR 相关问题请附上 `kb/*.log`）。

功能建议请说明使用场景：你手头是什么语料（课件格式、语言、是否扫描件），想解决什么问题。

## 提 pull request

- 一个 PR 只做一件事，标题写清改动范围。
- 提交信息用 `type: 说明`，type 取 `feat` / `fix` / `docs` / `refactor` / `chore`。
- 改完请自测：

  ```powershell
  .\tools\run.ps1 ingest      # 增量入库不应报错、不应重复入库
  .\tools\run.ps1 query "你的测试问题" -K 3
  python tools\eval_retrieval.py 3   # 检索回归，命中率不应下降
  ```

## 代码约定

- Python 3.9+，**只用标准库**（`pypdf` / `pdfplumber` / `python-pptx` / `python-docx` 是可选的
  文档抽取依赖，缺了要有降级路径）。引入新依赖请在 issue 里先讨论。
- 不要把外部程序的绝对路径写进代码：一律走 `ACCKB_*` 环境变量 → Codex 自带运行时 → 系统 PATH
  这条探测链（见 `tools/common.py`）。
- 中文是主要交互语言，注释和日志可以用中文，但标识符保持英文。

## 请不要提交语料

以下内容请留在本地，`.gitignore` 已排除：

- 课程课件、讲义、教材 PDF（版权属于授课教师与出版社）；
- 期刊论文 PDF（版权属于出版方）；
- 索引与中间产物（`kb/kb.sqlite`、`kb/extracted/`、`kb/ocr/`、`kb/tools/tessdata/`）。

想演示功能，用你自己写的、可以公开的样例文件，或在 issue 里描述结构即可。
