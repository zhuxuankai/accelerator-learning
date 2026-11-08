const fs = require("fs");

function fail(message, details = {}) {
  process.stdout.write(JSON.stringify({ status: "error", message, ...details }, null, 2) + "\n");
  process.exit(2);
}

const target = process.argv[2];
if (!target) fail("用法：node render_check.cjs <markdown>");

let MarkdownIt;
let texmath;
let katex;
try {
  MarkdownIt = require("markdown-it");
  texmath = require("markdown-it-texmath");
  katex = require("katex");
} catch (error) {
  fail("找不到 Markdown+Math 依赖，请先在项目根目录执行 npm install。", {
    detail: String(error.message || error),
  });
}

const text = fs.readFileSync(target, "utf8");
const scanText = text
  .replace(/```[\s\S]*?```/g, "")
  .replace(/`[^`\n]*`/g, "")
  .replace(/<!--[\s\S]*?-->/g, "");
const legacy = {
  inline_open: (scanText.match(/\\\(/g) || []).length,
  inline_close: (scanText.match(/\\\)/g) || []).length,
  display_open: (scanText.match(/\\\[/g) || []).length,
  display_close: (scanText.match(/\\\]/g) || []).length,
  tag_commands: (scanText.match(/\\tag(?![A-Za-z])/g) || []).length,
};
const dollarMarkers = (scanText.match(/\$\$/g) || []).length;
const md = new MarkdownIt({ html: true, linkify: true });
md.use(texmath, {
  engine: katex,
  delimiters: "dollars",
  katexOptions: { throwOnError: true, strict: "error" },
});

try {
  const html = md.render(text);
  const result = {
    status: Object.values(legacy).some((count) => count > 0) || dollarMarkers % 2 !== 0
      ? "warning"
      : "ok",
    target,
    formulas: (html.match(/class="katex"/g) || []).length,
    numbered_equations: (html.match(/class="eqno"/g) || []).length,
    katex_errors: (html.match(/katex-error/g) || []).length,
    double_dollar_markers: dollarMarkers,
    legacy_delimiters: legacy,
  };
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  process.exit(result.status === "ok" ? 0 : 1);
} catch (error) {
  fail(String(error.message || error), {
    target,
    double_dollar_markers: dollarMarkers,
    legacy_delimiters: legacy,
  });
}
