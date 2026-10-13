# -*- coding: utf-8 -*-
"""加速器学习驾驶舱 - 公共模块

本模块只读工作区内 config.json 允许的目录；索引与缓存都写在 kb/ 下。
不依赖系统 PATH：所有外部程序都用绝对路径调用。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- 路径常量
WS = Path(__file__).resolve().parents[1]          # 工作区根：academic learning
KB = WS / "kb"
TOOLS = WS / "tools"
ROADMAP = WS / "学习路线"

# ------------------------------------------------------------------ 外部程序探测
# 依次尝试：ACCKB_* 环境变量 -> Codex 自带运行时 -> 系统 PATH。
# 换机器时不需要改代码，装好 Python/Node/Poppler 或设一个环境变量即可。
_RUNTIME_ROOTS = [
    Path(p)
    for p in (
        os.environ.get("ACCKB_RUNTIME", ""),
        str(Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).parent
            / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"),
    )
    if p
]


def _find_tool(env_names: tuple[str, ...], runtime_rel: str, exe_names: tuple[str, ...], fallback=None):
    for name in env_names:
        value = os.environ.get(name)
        if value:
            candidate = Path(value)
            if candidate.exists():
                return candidate
    if runtime_rel:
        for root in _RUNTIME_ROOTS:
            candidate = root / runtime_rel
            if candidate.exists():
                return candidate
    for exe in exe_names:
        found = shutil.which(exe)
        if found:
            return Path(found)
    return fallback


PY = _find_tool(("ACCKB_PYTHON",), "python/python.exe", ("python", "python3"), Path(sys.executable))
NODE = _find_tool(("ACCKB_NODE",), "node/node.exe", ("node",), None)
# node_modules 优先用自带运行时里的那份（确定装了 tesseract.js），再退回环境变量
NODE_MODULES = _find_tool((), "node/node_modules", (), None) or _find_tool(
    ("ACCKB_NODE_MODULES", "NODE_PATH"), "", (), None
)
PDFTOPPM = _find_tool(
    ("ACCKB_PDFTOPPM",), "native/poppler/Library/bin/pdftoppm.exe", ("pdftoppm",), None
)
TESSDATA = KB / "tools" / "tessdata"
RENDER_TMP = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp") / "acc_kb_render"

CONFIG_PATH = KB / "config.json"
MANIFEST_PATH = KB / "manifest.json"
GLOSSARY_PATH = KB / "glossary.md"
DB_PATH = KB / "kb.sqlite"

# 中文二元切分用的字符类
CJK = r"\u4e00-\u9fff"
_CJK_RE = re.compile(f"[{CJK}]+")
_LATIN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\.\-]*")
_TOKEN_RE = re.compile(f"[{CJK}]+|[A-Za-z0-9][A-Za-z0-9_.\\-]*")

# 检索时忽略的高频虚词（中文按字符级别处理，这里列出常见的无信息量词）
STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "或", "我", "你", "他", "它",
    "这", "那", "什么", "怎么", "怎样", "如何", "为什么", "哪些", "哪个",
    "请", "帮", "讲", "说", "一", "下", "吗", "呢", "啊", "有", "没",
    "how", "what", "why", "the", "a", "an", "is", "are", "of", "to", "and",
    "please", "explain", "me", "my",
}


# ---------------------------------------------------------------- 基础工具
def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_config() -> dict:
    """读取 kb/config.json；没有就用 kb/config.example.json（新克隆的仓库可直接跑）。"""
    cfg = read_json(CONFIG_PATH, None)
    if cfg is None:
        example = KB / "config.example.json"
        cfg = read_json(example, None)
        if cfg is None:
            raise SystemExit(
                f"缺少配置文件：{CONFIG_PATH}（也没有找到 {example}）。"
                "请复制 kb/config.example.json 为 kb/config.json 后按需修改。"
            )
    return cfg


def sha1_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def slugify(rel_path: str) -> str:
    s = rel_path.replace("\\", "/")
    s = re.sub(r"[\\/:*?\"<>|]", "_", s)
    return s


def now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


# ---------------------------------------------------------------- 分词
def token_list(text: str) -> list[str]:
    """中文按二元切分，英文/数字按词切分（全部小写）。"""
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        t = m.group(0)
        if _CJK_RE.fullmatch(t):
            if len(t) == 1:
                out.append(t)
            else:
                out.extend(t[i : i + 2] for i in range(len(t) - 1))
        else:
            out.append(t.lower())
    return out


def tokenize(text: str) -> str:
    return " ".join(token_list(text))


def raw_terms(text: str) -> list[str]:
    """原始词元（中文整词 + 英文词），用于计算覆盖率。"""
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        t = m.group(0)
        if _CJK_RE.fullmatch(t):
            out.extend(ch for ch in t if ch not in STOPWORDS)
        else:
            t = t.lower()
            if t not in STOPWORDS:
                out.append(t)
    return out


def norm_text(text: str) -> str:
    """去掉空白与标点，用于短语匹配。"""
    s = re.sub(r"\s+", "", text.lower())
    return re.sub(r"[，。、；：？！（）《》“”‘’\[\]{}()<>\"'`,.;:!?/\\|~@#$%^&*+=_\-—…·]", "", s)


# ---------------------------------------------------------------- 术语表
def parse_glossary() -> list[list[str]]:
    """把 glossary.md 里的 `- A | B | C` 行解析成同义组。"""
    groups: list[list[str]] = []
    if not GLOSSARY_PATH.exists():
        return groups
    for line in GLOSSARY_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        parts = [p.strip() for p in line.lstrip("-").split("|")]
        parts = [p for p in parts if p and not p.startswith("#")]
        if len(parts) >= 2:
            groups.append(parts)
    return groups


def expand_terms(query: str) -> list[str]:
    """返回查询里命中的术语组所对应的额外检索词。"""
    q_norm = norm_text(query)
    extra: list[str] = []
    for group in parse_glossary():
        hit = False
        for term in group:
            t = norm_text(term)
            if t and (t in q_norm or (len(t) >= 2 and t in query.lower())):
                hit = True
                break
        if hit:
            for term in group:
                extra.extend(token_list(term))
    return extra


# ---------------------------------------------------------------- 版本归组
_VER_PATTERNS = [
    r"[-_—－]\s*\d{4}\s*$",        # -0923 / -0915
    r"[-_—－]\s*20\d{6}\s*$",      # -20260923
    r"\(\s*\d+\s*\)\s*$",          # (1)
    r"（\s*\d+\s*）\s*$",          # （1）
    r"[-_—－]\s*副本\s*$",
    r"[-_—－]\s*完整\s*$",
    r"[-_—－]\s*第?\d+版\s*$",
    r"[-_—－]\s*v\d+\s*$",
]


def version_key(rel_path: str) -> str:
    """把同一份讲义的不同日期/版本归到同一个 key。"""
    p = Path(rel_path)
    stem = p.stem
    prev = None
    while prev != stem:
        prev = stem
        for pat in _VER_PATTERNS:
            stem = re.sub(pat, "", stem, flags=re.IGNORECASE).strip()
    stem = re.sub(r"\s+", " ", stem)
    return f"{p.parent.as_posix()}/{stem}"


# ---------------------------------------------------------------- 分块
def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    """按自然段聚合到 max_chars，超长再滑窗切分。"""
    text = re.sub(r"[ \t]+", " ", text.replace("\u3000", " ")).strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        paras = [text]
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if not buf:
            buf = para
        elif len(buf) + len(para) + 1 <= max_chars:
            buf = f"{buf}\n{para}"
        else:
            chunks.extend(_split_long(buf, max_chars, overlap))
            buf = para
    if buf:
        chunks.extend(_split_long(buf, max_chars, overlap))
    return [c for c in chunks if c.strip()]


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out = []
    step = max(1, max_chars - overlap)
    for start in range(0, len(text), step):
        piece = text[start : start + max_chars]
        if piece.strip():
            out.append(piece)
        if start + max_chars >= len(text):
            break
    return out


# ---------------------------------------------------------------- 数据库
SCHEMA = """
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY,
  rel_path TEXT UNIQUE,
  title TEXT, course TEXT, kind TEXT,
  sha1 TEXT, mtime REAL,
  n_units INTEGER, n_chunks INTEGER,
  ocr_units INTEGER, ocr_ratio REAL,
  status TEXT, note TEXT,
  version_key TEXT, version_rank INTEGER, is_latest INTEGER,
  indexed_at TEXT
);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY,
  doc_id INTEGER,
  unit_label TEXT, part INTEGER,
  text TEXT, n_chars INTEGER, ocr INTEGER,
  is_latest INTEGER, course TEXT, kind TEXT, rel_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_latest ON chunks(is_latest);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(tok, tokenize='unicode61');
"""


def connect_db(readonly: bool = False) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    if not readonly:
        conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- OCR 辅助
def ensure_tessdata() -> Path:
    """确保 chi_sim / eng 语言包在 kb/tools/tessdata 下。"""
    TESSDATA.mkdir(parents=True, exist_ok=True)
    need = ["chi_sim.traineddata", "eng.traineddata"]
    missing = [n for n in need if not (TESSDATA / n).exists()]
    if not missing:
        return TESSDATA
    import gzip
    import urllib.request

    for name in missing:
        url = f"https://tessdata.projectnaptha.com/4.0.0/{name}.gz"
        print(f"[ocr] 下载语言包 {name} ...", flush=True)
        tmp = TESSDATA / f"{name}.gz"
        urllib.request.urlretrieve(url, tmp)
        with gzip.open(tmp, "rb") as src, (TESSDATA / name).open("wb") as dst:
            dst.write(src.read())
        tmp.unlink(missing_ok=True)
    return TESSDATA


def render_pages(pdf: Path, first: int, last: int, dpi: int, outdir: Path) -> dict[int, Path]:
    """用 poppler 把 [first,last] 页渲染成 PNG，返回 {页码: 路径}。"""
    outdir.mkdir(parents=True, exist_ok=True)
    prefix = outdir / "page"
    if not PDFTOPPM:
        raise RuntimeError(
            "找不到 pdftoppm（Poppler）。请安装 Poppler 并加入 PATH，"
            "或用环境变量 ACCKB_PDFTOPPM 指向 pdftoppm 可执行文件。"
        )
    cmd = [str(PDFTOPPM), "-r", str(dpi), "-f", str(first), "-l", str(last), "-png", str(pdf), str(prefix)]
    subprocess.run(cmd, check=True, capture_output=True)
    result: dict[int, Path] = {}
    for png in sorted(outdir.glob("page-*.png")):
        m = re.search(r"page-(\d+)\.png$", png.name)
        if m:
            result[int(m.group(1))] = png
    return result


def run_ocr_worker(images: list[Path], lang_path: Path, workdir: Path, workers: int) -> dict[str, dict]:
    """调用 node OCR worker，返回 {文件名: {text, confidence}}。"""
    if not images:
        return {}
    if not NODE:
        raise RuntimeError(
            "找不到 node。OCR 需要 Node.js：安装后加入 PATH，或用环境变量 ACCKB_NODE 指定路径。"
        )
    if not NODE_MODULES:
        raise RuntimeError(
            "找不到 tesseract.js。请执行 `npm install tesseract.js`，"
            "或用环境变量 ACCKB_NODE_MODULES 指向 node_modules 目录。"
        )
    list_path = workdir / "images.txt"
    out_path = workdir / "ocr.json"
    list_path.write_text("\n".join(str(p) for p in images), encoding="utf-8")
    script = TOOLS / "ocr_worker.cjs"
    env = dict(os.environ)
    env["NODE_PATH"] = str(NODE_MODULES)
    cmd = [
        str(NODE),
        str(script),
        str(lang_path),
        str(workdir / "tcache"),
        str(list_path),
        str(out_path),
        str(max(1, workers)),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace")[-2000:]
        raise RuntimeError(f"OCR worker 失败（exit={proc.returncode}）：{err}")
    data = json.loads(out_path.read_text(encoding="utf-8"))
    return {item["file"]: item for item in data}


def eprint(*args) -> None:
    print(*args, file=sys.stderr, flush=True)
