# -*- coding: utf-8 -*-
"""论文语料抓取：INSPIRE（主）+ OpenAlex（OA 链接）+ arXiv（全文）

默认 --dry-run：只打印候选表并写出 kb/papers/候选清单.md，不下载。
加 --write 才下载 PDF 到 文献/，并生成阅读清单与待获取清单。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KB, WS, load_config, now_iso, read_json, write_json  # noqa: E402

UA = "academic-learning-kb/1.0 (personal study index)"
PAPER_DIR = WS / "文献"
META_PATH = KB / "papers" / "metadata.jsonl"
READING_LIST = KB / "papers" / "阅读清单.md"
PENDING_LIST = KB / "papers" / "待获取清单.md"
CANDIDATE_MD = KB / "papers" / "候选清单.md"

CORE_VENUES = (
    "physical review accelerators and beams", "physical review special topics",
    "nuclear instruments and methods", "journal of synchrotron radiation",
    "high power laser science and engineering", "frontiers in physics",
    "physical review letters", "physical review x", "new journal of physics",
    "optics express", "optics letters", "applied physics letters",
    "ieee transactions on applied superconductivity", "nature photonics",
    "chinese optics letters", "radiation detection technology and methods",
    "physical review research", "physical review applied", "physics of plasmas",
)

# INSPIRE 用期刊缩写，先展开再匹配
JOURNAL_ABBREV = {
    "phys.rev.lett.": "physical review letters",
    "phys.rev.x": "physical review x",
    "phys.rev.st accel.beams": "physical review accelerators and beams",
    "phys.rev.accel.beams": "physical review accelerators and beams",
    "phys.rev.research": "physical review research",
    "phys.rev.applied": "physical review applied",
    "phys.rev.a": "physical review a",
    "phys.rev.e": "physical review e",
    "rev.mod.phys.": "reviews of modern physics",
    "new j.phys.": "new journal of physics",
    "jinst": "journal of instrumentation",
    "j.synchrotron rad.": "journal of synchrotron radiation",
    "nucl.instrum.meth.": "nuclear instruments and methods",
    "nature photon.": "nature photonics",
    "nature commun.": "nature communications",
    "sci.rep.": "scientific reports",
    "opt.express": "optics express",
    "opt.lett.": "optics letters",
    "appl.phys.lett.": "applied physics letters",
    "phys.plasmas": "physics of plasmas",
    "ieee trans.appl.supercond.": "ieee transactions on applied superconductivity",
    "front.phys.": "frontiers in physics",
    "high power laser sci.eng.": "high power laser science and engineering",
    "chin.opt.lett.": "chinese optics letters",
    "phys.scripta": "physica scripta",
    "j.phys.conf.ser.": "journal of physics conference series",
}


def normalize_journal(name: str) -> str:
    key = (name or "").strip().lower()
    if not key:
        return ""
    if key in JOURNAL_ABBREV:
        return JOURNAL_ABBREV[key]
    for abbrev, full in JOURNAL_ABBREV.items():
        if key.startswith(abbrev):
            return full
    return key


def http_json(url: str, tries: int = 3, sleep: float = 2.0):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(sleep * (attempt + 1))
    print(f"[warn] 请求失败 {url} -> {last}", file=sys.stderr)
    return None


def http_download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read()
        if "pdf" not in ctype.lower() and not data[:4] == b"%PDF":
            print(f"[skip] 非 PDF 内容：{url} ({ctype})", file=sys.stderr)
            return False
        if len(data) < 60_000:
            print(f"[skip] 文件过小：{url} ({len(data)} bytes)", file=sys.stderr)
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[skip] 下载失败 {url} -> {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------- INSPIRE
def inspire_author_papers(recid: int, since_year: int) -> list[dict]:
    fields = "titles,publication_info,dois,arxiv_eprints,abstracts,citation_count,document_type,authors,earliest_date"
    out: list[dict] = []
    page = 1
    while page <= 6:
        url = (
            f"https://inspirehep.net/api/literature?q=authors.recid%3A{recid}"
            f"&size=100&page={page}&sort=mostrecent&fields={fields}"
        )
        data = http_json(url)
        if not data:
            break
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        stop = True
        for hit in hits:
            meta = hit.get("metadata", {})
            year = _year_of(meta)
            if year and year >= since_year:
                stop = False
                out.append(meta)
        if stop:
            break
        page += 1
        time.sleep(1.0)
    return out


def inspire_search(query: str, size: int = 10) -> list[dict]:
    fields = "titles,publication_info,dois,arxiv_eprints,abstracts,citation_count,document_type,authors,earliest_date"
    url = (
        "https://inspirehep.net/api/literature?q="
        + urllib.parse.quote(f'"{query}"')
        + f"&size={size}&fields={fields}"
    )
    data = http_json(url)
    if not data:
        return []
    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        url2 = (
            "https://inspirehep.net/api/literature?q="
            + urllib.parse.quote(query)
            + f"&size={size}&fields={fields}"
        )
        data2 = http_json(url2)
        hits = (data2 or {}).get("hits", {}).get("hits", [])
    return [h.get("metadata", {}) for h in hits]


def crossref_search(title: str, size: int = 5) -> list[dict]:
    """Crossref 标题检索：对 Nature Photonics / HPLSE / Frontiers 这类期刊覆盖好。"""
    url = (
        "https://api.crossref.org/works?query.bibliographic="
        + urllib.parse.quote(title)
        + f"&rows={size}&select=title,DOI,issued,container-title,author,is-referenced-by-count&mailto=academic-learning@example.com"
    )
    data = http_json(url)
    if not data:
        return []
    out = []
    for item in data.get("message", {}).get("items", []):
        titles = item.get("title") or []
        issued = (item.get("issued") or {}).get("date-parts") or [[0]]
        year = issued[0][0] if issued and issued[0] else 0
        container = (item.get("container-title") or [""])[0]
        out.append(
            {
                "title": re.sub(r"\s+", " ", titles[0]).strip() if titles else "",
                "year": year or 0,
                "journal": container,
                "doi": item.get("DOI", ""),
                "arxiv": "",
                "abstract": "",
                "citations": item.get("is-referenced-by-count", 0),
                "authors": [
                    f"{a.get('family', '')} {a.get('given', '')}".strip()
                    for a in item.get("author", [])
                ],
                "doc_types": ["article"],
            }
        )
    return out


def unpaywall(doi: str, mailto: str) -> dict:
    if not doi:
        return {}
    url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={urllib.parse.quote(mailto)}"
    data = http_json(url, tries=2, sleep=1.5)
    if not data:
        return {}
    best = data.get("best_oa_location") or {}
    return {
        "is_oa": bool(data.get("is_oa")),
        "pdf_url": best.get("url_for_pdf") or best.get("url") or "",
    }


def openalex_title_search(title: str, size: int = 5) -> list[dict]:
    """OpenAlex 标题检索（比 INSPIRE 覆盖广，但需限速）。"""
    url = (
        "https://api.openalex.org/works?filter=title.search:"
        + urllib.parse.quote(title)
        + f"&per-page={size}&mailto=academic-learning@example.com"
    )
    data = http_json(url, tries=4, sleep=3.0)
    if not data:
        return []
    out = []
    for work in data.get("results", []):
        source = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        best = work.get("best_oa_location") or {}
        out.append(
            {
                "title": work.get("title") or "",
                "year": work.get("publication_year") or 0,
                "journal": source,
                "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
                "arxiv": "",
                "abstract": "",
                "citations": work.get("cited_by_count", 0),
                "authors": [
                    (a.get("author") or {}).get("display_name", "")
                    for a in work.get("authorships", [])
                ],
                "doc_types": ["article"],
                "_oa_pdf": best.get("pdf_url") or "",
                "_is_oa": bool(work.get("is_oa")),
            }
        )
    return out


def arxiv_search(title: str, size: int = 5) -> list[dict]:
    """arXiv API 按标题检索，返回规范化后的记录。"""
    import xml.etree.ElementTree as ET

    url = (
        "http://export.arxiv.org/api/query?search_query="
        + urllib.parse.quote(f'ti:"{title}"')
        + f"&start=0&max_results={size}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] arXiv 检索失败：{exc}", file=sys.stderr)
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    for entry in root.findall("a:entry", ns):
        title_txt = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        published = entry.findtext("a:published", default="", namespaces=ns) or ""
        arxiv_id = (entry.findtext("a:id", default="", namespaces=ns) or "").rsplit("/", 1)[-1]
        journal = entry.find("{http://arxiv.org/schemas/atom}journal_ref")
        out.append(
            {
                "title": re.sub(r"\s+", " ", title_txt),
                "year": int(published[:4]) if published[:4].isdigit() else 0,
                "journal": journal.text.strip() if journal is not None and journal.text else "arXiv",
                "doi": "",
                "arxiv": arxiv_id,
                "abstract": summary,
                "citations": 0,
                "authors": [
                    a.findtext("a:name", default="", namespaces=ns)
                    for a in entry.findall("a:author", ns)
                ],
                "doc_types": ["article"],
            }
        )
    return out


def title_similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    def norm(s: str) -> str:
        s = re.sub(r"<[^>]+>", " ", s or "")
        return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def resolve_classic(title: str) -> tuple[dict | None, float]:
    """在 INSPIRE / OpenAlex / arXiv 上解析标题，返回（最优记录, 相似度）。

    检索源本身的标题匹配比较宽松，所以一律用 difflib 复核对齐程度。
    """
    best: dict | None = None
    best_ratio = 0.0
    for meta in inspire_search(title, size=10):
        paper = normalize(meta)
        ratio = title_similarity(title, paper["title"])
        if ratio > best_ratio:
            best, best_ratio = paper, ratio
    time.sleep(0.8)
    if best_ratio < 0.85:
        for paper in crossref_search(title, size=5):
            ratio = title_similarity(title, paper["title"])
            if ratio > best_ratio:
                best, best_ratio = paper, ratio
        time.sleep(0.8)
    if best_ratio < 0.85:
        for paper in arxiv_search(title, size=5):
            ratio = title_similarity(title, paper["title"])
            if ratio > best_ratio:
                best, best_ratio = paper, ratio
        time.sleep(1.0)
    return best, best_ratio


def _year_of(meta: dict) -> int:
    info = (meta.get("publication_info") or [{}])[0]
    year = info.get("year")
    if isinstance(year, int):
        return year
    date = meta.get("earliest_date") or ""
    m = re.match(r"(\d{4})", str(date))
    return int(m.group(1)) if m else 0


def normalize(meta: dict) -> dict:
    titles = meta.get("titles") or [{}]
    info = (meta.get("publication_info") or [{}])[0]
    authors = meta.get("authors") or []
    arxiv = (meta.get("arxiv_eprints") or [{}])[0].get("value")
    abstract = (meta.get("abstracts") or [{}])[0].get("value", "")
    return {
        "title": titles[0].get("title", "").strip(),
        "year": _year_of(meta),
        "journal": (info.get("journal_title") or "").strip(),
        "doi": ((meta.get("dois") or [{}])[0].get("value") or "").strip(),
        "arxiv": arxiv or "",
        "abstract": re.sub(r"<[^>]+>", "", abstract).strip(),
        "citations": int(meta.get("citation_count") or 0),
        "authors": [a.get("full_name", "") for a in authors],
        "doc_types": meta.get("document_type") or [],
    }


# ---------------------------------------------------------------- 主题与筛选
def topic_hits(paper: dict, keywords: list[str]) -> list[str]:
    blob = f"{paper['title']} {paper['abstract']}".lower()
    return [kw for kw in keywords if kw.lower() in blob]


def core_venue(paper: dict) -> bool:
    j = normalize_journal(paper["journal"])
    return any(v in j for v in CORE_VENUES)


def is_accelerator_paper(paper: dict) -> bool:
    dt = " ".join(paper["doc_types"]).lower()
    if dt and not any(k in dt for k in ("article", "conference", "proceedings", "thesis")):
        return False
    return True


# ---------------------------------------------------------------- OpenAlex
def openalex_oa_map(dois: list[str], mailto: str) -> dict[str, dict]:
    """按 DOI 批量取 OA 链接与引用数。"""
    out: dict[str, dict] = {}
    batch = 25
    for start in range(0, len(dois), batch):
        chunk = [d for d in dois[start : start + batch] if d]
        if not chunk:
            continue
        url = (
            "https://api.openalex.org/works?filter=doi:"
            + "|".join(chunk)
            + f"&per-page={batch}&mailto={mailto}"
        )
        data = http_json(url)
        if not data:
            continue
        for work in data.get("results", []):
            doi = (work.get("doi") or "").replace("https://doi.org/", "").lower()
            best = work.get("best_oa_location") or {}
            out[doi] = {
                "is_oa": bool(work.get("is_oa")),
                "pdf_url": best.get("pdf_url") or "",
                "landing": best.get("landing_page_url") or "",
                "cited_by": work.get("cited_by_count", 0),
            }
        time.sleep(2.5)
    return out


# ---------------------------------------------------------------- 文件名
def ascii_slug(text: str, limit: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:limit] or "paper"


def pdf_name(paper: dict) -> str:
    first = ""
    if paper["authors"]:
        first = paper["authors"][0].split(",")[0].strip().split(" ")[-1]
    first = ascii_slug(first, 20) or "anon"
    return f"{paper['year'] or 'na'}_{first}_{ascii_slug(paper['title'])}.pdf"


# ---------------------------------------------------------------- 主流程
def build_candidates(cfg: dict) -> tuple[list[dict], list[str]]:
    pcfg = cfg["papers"]
    keywords = pcfg["topic_keywords"]
    since = int(pcfg["since_year"])
    cands: list[dict] = []
    seen: set[str] = set()

    def key_of(p: dict) -> str:
        return p["doi"].lower() or p["arxiv"] or re.sub(r"\W+", "", p["title"].lower())[:80]

    recid = pcfg.get("inspire_author_recid")
    if recid:
        print(f"[1/3] 抓取 INSPIRE 作者档案 recid={recid} ...", flush=True)
        group = [normalize(m) for m in inspire_author_papers(int(recid), since)]
    else:
        print("[1/3] 未配置 inspire_author_recid，跳过作者档案抓取（参见 kb/config.example.json）", flush=True)
        group = []
    for paper in group:
        if not is_accelerator_paper(paper):
            continue
        hits = topic_hits(paper, keywords)
        if not hits:
            continue
        k = key_of(paper)
        if k in seen:
            continue
        seen.add(k)
        priority = "P1" if core_venue(paper) else "P2"
        cands.append({**paper, "source": "inspire", "topics": hits, "priority": priority})

    print(f"[2/3] 解析奠基经典（{len(pcfg['classics'])} 条精确标题）...", flush=True)
    unmatched = []
    by_key = {key_of(c): c for c in cands}
    for item in pcfg["classics"]:
        title = item.get("title") or item.get("query", "")
        search_hint = item.get("search") or title

        # 先看是否已经在组内论文池里（省一次网络请求，也更准）
        pool_hit, pool_ratio, pool_key = None, 0.0, ""
        for k, cand in by_key.items():
            ratio = title_similarity(title, cand["title"])
            if ratio > pool_ratio:
                pool_hit, pool_ratio, pool_key = cand, ratio, k

        if pool_hit is not None and pool_ratio >= 0.85:
            pool_hit["priority"] = "P0"
            pool_hit["note"] = item.get("note", "")
            pool_hit["match_ratio"] = round(pool_ratio, 3)
            pool_hit["query_title"] = title
            pool_hit.setdefault("source", "classic")
            print(f"  [命中组内 {pool_ratio:.2f}] {pool_hit['title'][:80]}")
            continue

        paper, ratio = resolve_classic(search_hint)
        if paper is None or ratio < 0.72:
            unmatched.append(title)
            print(f"  [未匹配] {title}（最高相似度 {ratio:.2f}）")
            continue
        k = key_of(paper)
        if k in seen:
            continue
        seen.add(k)
        cands.append(
            {
                **paper,
                "source": "classic",
                "topics": topic_hits(paper, keywords) or ["经典"],
                "priority": "P0",
                "note": item.get("note", ""),
                "match_ratio": round(ratio, 3),
                "query_title": title,
            }
        )
        by_key[k] = cands[-1]
        print(f"  [匹配 {ratio:.2f}] {paper['title'][:80]}")

    print(f"[3/4] 用 Unpaywall 补开放获取链接（{len(cands)} 篇）...", flush=True)
    mailto = pcfg.get("mailto", "")
    unpaywall_ok = bool(mailto) and "example.com" not in mailto
    if not unpaywall_ok:
        print("  （未配置可用邮箱，跳过 Unpaywall，改用 OpenAlex）")
    for c in cands:
        c["cited_by"] = c.get("citations", 0) or c.get("cited_by", 0)
        info = unpaywall(c["doi"], mailto) if (unpaywall_ok and c.get("doi")) else {}
        if info:
            c["oa"] = bool(info.get("is_oa"))
            c["pdf_url"] = info.get("pdf_url", "")
        else:
            c.setdefault("oa", False)
            c.setdefault("pdf_url", "")
        if c.get("_oa_pdf") and not c["pdf_url"]:
            c["pdf_url"] = c["_oa_pdf"]
            c["oa"] = True
        if not c["pdf_url"] and c.get("arxiv"):
            c["pdf_url"] = f"https://arxiv.org/pdf/{c['arxiv']}"
            c["oa"] = True
        if unpaywall_ok:
            time.sleep(0.35)

    print(f"[4/4] 用 OpenAlex 补齐缺失的 OA 与引用数 ...", flush=True)
    need = [c for c in cands if c.get("doi") and (not c.get("pdf_url") or not c.get("cited_by"))]
    if need:
        oa = openalex_oa_map([c["doi"] for c in need], mailto)
        for c in need:
            info = oa.get(c["doi"].lower())
            if not info:
                continue
            if not c.get("pdf_url") and info.get("pdf_url"):
                c["pdf_url"] = info["pdf_url"]
                c["oa"] = True
            c["cited_by"] = max(c.get("cited_by", 0), info.get("cited_by", 0))
    return cands, unmatched


def write_candidate_md(cands: list[dict], unmatched: list[str]) -> None:
    lines = ["# 论文候选清单", "", f"生成时间：{now_iso()}", ""]
    lines.append(f"合计 {len(cands)} 篇；P0 经典 {sum(1 for c in cands if c['priority'] == 'P0')}，"
                 f"P1 组内核心 {sum(1 for c in cands if c['priority'] == 'P1')}，"
                 f"P2 其它 {sum(1 for c in cands if c['priority'] == 'P2')}")
    lines.append("")
    for pri in ("P0", "P1", "P2"):
        subset = [c for c in cands if c["priority"] == pri]
        if not subset:
            continue
        subset.sort(key=lambda c: (-c.get("cited_by", 0), -c["year"]))
        lines.append(f"## {pri}（{len(subset)} 篇）")
        lines.append("")
        lines.append("| # | 年份 | 标题 | 期刊 | 引用 | OA | 匹配度 | arXiv |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for i, c in enumerate(subset, 1):
            title = c["title"].replace("|", "/")
            ratio = c.get("match_ratio")
            lines.append(
                f"| {i} | {c['year']} | {title} | {c['journal'] or '—'} | {c.get('cited_by', 0)} | "
                f"{'是' if c.get('oa') else '否'} | {f'{ratio:.2f}' if ratio else '—'} | {c['arxiv'] or '—'} |"
            )
        lines.append("")
    if unmatched:
        lines += [f"## 未能匹配的经典检索式（{len(unmatched)} 条，需人工确认）", ""]
        lines += [f"- {u}" for u in unmatched]
        lines.append("")
    CANDIDATE_MD.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE_MD.write_text("\n".join(lines), encoding="utf-8")


def download_all(cands: list[dict]) -> tuple[list[dict], list[dict]]:
    got, pending = [], []
    for c in cands:
        url = c.get("pdf_url") or (f"https://arxiv.org/pdf/{c['arxiv']}" if c["arxiv"] else "")
        if not url:
            pending.append(c)
            continue
        dest = PAPER_DIR / pdf_name(c)
        if dest.exists() or http_download(url, dest):
            c["local_pdf"] = str(dest.relative_to(WS)).replace("\\", "/")
            got.append(c)
        else:
            pending.append(c)
        time.sleep(0.8)

    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    with META_PATH.open("w", encoding="utf-8") as fh:
        for c in got:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    READING_LIST.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 阅读清单", "", f"更新时间：{now_iso()}　共 {len(got)} 篇", ""]
    by_year: dict[int, list[dict]] = {}
    for c in got:
        by_year.setdefault(c["year"], []).append(c)
    for year in sorted(by_year, reverse=True):
        lines.append(f"## {year}")
        lines.append("")
        for c in sorted(by_year[year], key=lambda x: (x["priority"], -x.get("cited_by", 0))):
            lines.append(
                f"- [{c['priority']}] {c['title']}（{c['journal'] or 'preprint'}，"
                f"引用 {c.get('cited_by', 0)}）`{c['local_pdf']}`"
            )
        lines.append("")
    READING_LIST.write_text("\n".join(lines), encoding="utf-8")

    plines = ["# 待获取清单（非开放获取）", "", f"更新时间：{now_iso()}　共 {len(pending)} 篇", ""]
    for c in pending:
        link = f"https://doi.org/{c['doi']}" if c["doi"] else "—"
        plines.append(f"- {c['year']} {c['title']}（{c['journal'] or '—'}）{link}")
    PENDING_LIST.write_text("\n".join(plines), encoding="utf-8")
    return got, pending


def main() -> None:
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只出候选表（默认行为）")
    ap.add_argument("--write", action="store_true", help="下载 PDF 并写清单")
    ap.add_argument("--priorities", default="", help="只处理指定优先级，如 P0 或 P0,P1")
    args = ap.parse_args()

    cands, unmatched = build_candidates(cfg)
    write_candidate_md(cands, unmatched)
    if args.priorities:
        wanted = {p.strip().upper() for p in args.priorities.split(",") if p.strip()}
        cands = [c for c in cands if c["priority"] in wanted]
        print(f"按优先级过滤后剩 {len(cands)} 篇：{','.join(sorted(wanted))}")
    print(f"\n候选 {len(cands)} 篇，清单已写入 {CANDIDATE_MD.relative_to(WS)}")
    oa_n = sum(1 for c in cands if c.get("oa"))
    print(f"其中可拿全文（OA/arXiv）：{oa_n} 篇，需另找：{len(cands) - oa_n} 篇")
    for pri in ("P0", "P1", "P2"):
        subset = [c for c in cands if c["priority"] == pri]
        if not subset:
            continue
        print(f"\n== {pri}（{len(subset)} 篇，按引用排序前 8）==")
        for c in sorted(subset, key=lambda x: -x.get("cited_by", 0))[:8]:
            print(f"  [{c['year']}] {c['title'][:90]}  | {c['journal'] or 'preprint'} | 引 {c.get('cited_by', 0)} | OA={c.get('oa')}")
    if unmatched:
        print(f"\n未能匹配的经典标题 {len(unmatched)} 条：")
        for item in unmatched:
            print(f"  - {item}")

    if args.write:
        got, pending = download_all(cands)
        print(f"\n已下载 {len(got)} 篇到 文献/，待获取 {len(pending)} 篇（见 {PENDING_LIST.relative_to(WS)}）")
    else:
        print("\n（dry-run：未下载。确认后加 --write）")


if __name__ == "__main__":
    main()
