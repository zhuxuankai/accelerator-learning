# 翻译与 Markdown+Math

## 工作流

```powershell
pwsh extensions/translation/translation.ps1 -Status
pwsh extensions/translation/translation.ps1 -Prepare "文献/<file>.pdf"
pwsh extensions/translation/translation.ps1 -Audit
pwsh extensions/translation/translation.ps1 -RenderCheck "文献/译文/<file>.zh.md"
```

译本使用同名 `.zh.md`，逐页写 `<!-- pN -->` 锚点，页头维护“已译页”和“译本状态”。参考文献页也要保留锚点，可注明“未逐条翻译”。交付前必须完成页级审计和物理通读校对，末尾保留 `## 校对记录`。

## Markdown+Math 兼容

- 行内公式：`$...$`。
- 独立公式：`$$` 开始、`$$` 结束；编号写在闭合的 `$$` 后，如 `$$...$$ (42)`。
- 不使用 `\(...\)`、`\[...\]` 或数学模式内的 `\tag`。
- 数学模式内不写中文；中文解释放在公式外。
- 不用 Unicode 纯文本替代 LaTeX。
- `-Audit` 通过只证明页数、占位符和基础语法合格，不证明实际渲染或物理表述正确。

用户报告公式标红或整段无法渲染时，先运行 `-RenderCheck`。若解析器无错误但编辑器仍异常，生成 HTML 阅读版作为回退，并区分“内容错误”“解析错误”“编辑器缓存/兼容问题”。

OCR 质量低或 PDF 抽取导致公式残缺时，明确标注原页并说明未猜测补全。
