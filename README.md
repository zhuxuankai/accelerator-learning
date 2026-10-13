# 加速器学习驾驶舱

把"课程课件 + 论文"变成**可检索、带出处**的本地知识库，并自动维护一份学习路线。
为加速器物理方向的研究生写的，也可以直接搬到别的专业用——改课程目录名和文献关键词即可。

核心是一套零依赖的 Python/Node 脚本：抽取 → 分块 → SQLite FTS5 索引 → 检索；
再叠一层"每周维护"（增量入库 → 覆盖度 → 看板 → 下周计划）。

**工作区就是本仓库根目录**，脚本自动推导，不需要改任何路径。

## 语料边界（硬约束）

索引只覆盖两类材料，其他目录一律不读：

1. 课程目录：`kb/config.json` 里 `include_dirs` 列出的那几个（默认模板是 `课程一/`、`课程二/`）；
2. 联网下载的论文：`文献/`

`kb/`（索引与中间产物）、`tools/`（脚本）、`学习路线/`（路线与看板）是产物，不是语料。

**这些语料不进版本库**：课程课件与期刊论文有版权，且教材扫描件动辄上百 MB、超过 GitHub
的单文件硬上限。仓库只维护"系统"本身，语料在本地重建。

## 目录结构

```
tools/                     run.ps1（统一入口）与全部 Python/Node 脚本
kb/config.example.json     配置模板（复制成 config.json 后按需改）
kb/glossary.md             术语表：中英对照，检索扩展用
kb/eval/questions.jsonl    检索回归题库
学习路线/学习路线.example.md   学习路线模板
学习路线/进度追踪.example.csv  进度表模板
AGENTS.md                  本工作区给 Codex 的行为规则
```

仓库里**只有模板**。你自己的 `kb/config.json`、`kb/papers/`、`学习路线/学习路线.md`、
`进度追踪.csv`、`覆盖度.md`、`dashboard.html`、`周计划/` 都在 `.gitignore` 里，
只留在本机、不会被提交——想公开分享自己的版本时再手动去掉对应规则。

## 快速上手

在仓库根目录执行（统一走 `run.ps1`，它自己会探测 Python / Node / Poppler）：

```powershell
.\tools\run.ps1 status                              # 看知识库与进度概况
.\tools\run.ps1 plan                                # 查看本周任务清单（只读，不改任何文件）
.\tools\run.ps1 query "BPM 怎么测横向位置" -K 5      # 检索，返回带出处的 JSON
.\tools\run.ps1 query "分流阻抗" -Course 直线加速器    # 限定课程
.\tools\run.ps1 ingest                             # 增量入库（新课件丢进课程目录后执行）
.\tools\run.ps1 papers                             # 生成论文候选清单（默认不下载）
.\tools\run.ps1 weekly                             # 每周维护：入库→覆盖度→看板→本周与下周计划
```

检索回归测试（默认看 top-3 命中率）：

```powershell
.\tools\run.ps1 eval 3
```

## 工作原理

- **抽取**：PyPDF 逐页抽文本（快），稀疏页再用 pdfplumber 复核（准）；PPTX 走 python-pptx
  （含备注），DOCX 走 python-docx。
- **OCR**：整份扫描件用 poppler 渲染 220 DPI + tesseract.js（`chi_sim+eng`），结果缓存到
  `kb/ocr/`，第二次运行不重跑；OCR 块在排序里降权，公式是乱码、不作为引用依据。
- **索引**：SQLite FTS5，中文按二元切分后用 `unicode61` 建索引，`bm25()` 排序；
  检索 = 术语表同义扩展 → 召回 → 重排（词覆盖 + 短语命中 + 课程加权）。
- **版本去重**：同一份讲义的多个日期版本按"课程 + 标题主干"归组，默认只召回最新版，
  需要看演进时给 `query` 加 `-AllVersions`。
- **评测**：`kb/eval/questions.jsonl` 有 20 道真实问题，每周维护后回归一次。

## 每周自动维护

每周五 21:00 有一条 heartbeat 自动化「每周学习路线维护」挂在本仓库对应的对话上，动作是
`run.ps1 weekly`，然后汇报：新增语料、下周读的两篇论文、下周仿真任务、课程薄弱点。
无变化时保持静默。

## 进度回填纪律

`学习路线/进度追踪.csv` 每行带 `来源` 字段：`已确认`（用户说过或以产出为证）/ `推断`（系统推测）。
系统只把 `推断` 项列为待确认，不会自动打勾。

## 环境依赖

只有 Python 是必需的，其余按需：

| 组件 | 用途 | 是否必需 |
|---|---|---|
| Python 3.9+ | 全部脚本 | 必需 |
| `pypdf` / `pdfplumber` | PDF 抽文本 | 读 PDF 时需要 |
| `python-pptx` / `python-docx` | 抽 PPTX / DOCX | 读这些格式时需要 |
| Node.js + `tesseract.js` | 扫描件 OCR | 仅 OCR 时需要 |
| Poppler（`pdftoppm`） | 把 PDF 渲染成图给 OCR | 仅 OCR 时需要 |
| OCR 语言包 | `chi_sim` + `eng` | 首次 OCR 时自动下载到 `kb/tools/tessdata/`（约 68 MB，不入库） |

程序按 **`ACCKB_*` 环境变量 → Codex 自带运行时 → 系统 PATH** 的顺序自动探测，换机器不用改代码：

| 环境变量 | 覆盖的对象 |
|---|---|
| `ACCKB_PYTHON` | Python 解释器 |
| `ACCKB_NODE` | Node.js |
| `ACCKB_NODE_MODULES` | 含 `tesseract.js` 的 node_modules |
| `ACCKB_PDFTOPPM` | Poppler 的 `pdftoppm` 可执行文件 |
| `ACCKB_RUNTIME` | 整个运行时根目录 |

## 给别人用 / 换专业怎么改

1. `git clone` 之后，把 `kb/config.example.json` 复制成 `kb/config.json`，
   再把 `include_dirs` 改成你自己的课程目录名；
2. 每个课程目录里放课件（PDF / PPTX / DOCX / MD 都行）；
3. 论文语料改 `kb/config.json` 的 `papers` 段（作者、主题关键词、经典文献标题），
   跑 `.\tools\run.ps1 papers` 看候选清单，确认后加 `-Write` 下载开放获取的全文；
4. `kb/glossary.md` 换成你领域的中英术语对照表——它直接决定检索召回率；
5. `kb/eval/questions.jsonl` 换成你自己的 20 道真实问题，作为回归基线；
6. 把 `学习路线/学习路线.example.md` 与 `进度追踪.example.csv` 复制成去掉 `.example`
   的正式文件，写你自己的路线与进度（这两份默认不进仓库）。

## 许可证与贡献

MIT（见 [LICENSE](LICENSE)）。欢迎提 issue 和 PR，规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。
**请不要提交课程课件与论文 PDF**——`.gitignore` 已经排除了这些路径。

## 配套技能

个人技能 `accelerator-study-copilot`（装在 `$CODEX_HOME/skills/`，即默认的
`~/.codex/skills/`；源码副本在本仓库 `tools/skill-src/`）负责检索答疑、每周规划与进度回填，并在需要时路由到
`deep-research` / `academic-paper` / `academic-paper-reviewer` / `academic-pipeline` / `ppt-master-skill`。

## 同步到 GitHub

远端仓库：`https://github.com/zhuxuankai/accelerator-learning`（公开，MIT 许可）。
欢迎 fork 之后提 issue 或 PR——**请不要提交课程课件与论文 PDF**，见 [CONTRIBUTING.md](CONTRIBUTING.md)。

日常维护就是常规三步：

```powershell
git add -A
git commit -m "更新学习路线与知识库配置"
git push
```

几点约定：

- 凭据放在 Windows 凭据管理器里（Git Credential Manager），**不写进仓库、不写进脚本**。
- 每周自动化只改本地文件（覆盖度、看板、周计划），需要备份时手动 `git push` 一次即可。
- 课件与论文 PDF 不进版本库（版权 + 单文件超 GitHub 上限），只维护"系统"本身；
  语料按 README 上文的方式在本地重建。
- 提交身份配置在本仓库的局部配置里（`zhuxuankai` + GitHub noreply 邮箱），不影响其它仓库。
