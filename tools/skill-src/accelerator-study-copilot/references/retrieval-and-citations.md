# 检索与出处

在工作区根目录运行：

```powershell
pwsh tools/run.ps1 query "<问题>" -Mode <hybrid|lexical> [-Course <目录>] [-Kind <类型>] [-K 8] [-AllVersions]
```

## 模式选择

- 使用 `hybrid`：自然语言概念题、中文问法对应英文术语、多种可能说法、需要语义关联。
- 使用 `lexical`：文件名、公式号、缩写、模型名、装置名、明确原文片段或只查一个专有术语。
- 先用更窄的 `-Course` 或 `-Kind` 过滤；结果稀疏时才扩大范围。

## 阅读返回

- `status=ok`：从 `results` 综合回答，不逐条倾倒 JSON。
- `status=no_match`：明确说当前语料没有匹配，再决定是否按物理常识补充并标注“非课件内容”。
- 非零错误：区分索引缺失、配置损坏和依赖缺失，给出必要的 `doctor`/`index` 修复命令。
- `diagnostics.warnings` 必须处理：
  - `ambiguous`：保留版本不确定性，不自行宣称最新。
  - `ocr_quality=low`：只用于定位；不得把 OCR 内容作为公式或数字原文。
  - 同一文档最多保留若干片段；需要更多上下文时继续查下一张/页。

## 回答格式

- 先给结论，再解释物理图像。
- 每个课件事实附 `rel_path + unit_label`，如 `束线光学/讲义.pdf 页12`。
- 术语保留英文；公式使用 LaTeX。
- 检索证据不足时说明缺口，不编造页码或公式。
