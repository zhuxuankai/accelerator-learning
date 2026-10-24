from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import tempfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import CockpitError, Paths

SUPPORTED_SUFFIXES = {".pdf", ".pptx", ".docx", ".md", ".txt"}
NOISE_CHARS = set("/\\|=_^{}[]<>$")
_RAPIDOCR_ENGINE = None


@dataclass
class Unit:
    unit: int
    unit_label: str
    text: str
    ocr: bool
    ocr_confidence: float
    ocr_quality: str
    semantic_eligible: bool
    replacement_ratio: float
    noise_ratio: float
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha1_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def quality_metrics(text: str, confidence: float = 1.0) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {
            "ocr_quality": "empty",
            "semantic_eligible": False,
            "replacement_ratio": 1.0,
            "noise_ratio": 1.0,
            "confidence": confidence,
        }
    replacement_ratio = (stripped.count("\ufffd") + stripped.count("(cid:")) / len(stripped)
    visible = [char for char in stripped if not char.isspace()]
    noise_ratio = sum(char in NOISE_CHARS for char in visible) / max(1, len(visible))
    counts = Counter(stripped.replace("\n", ""))
    entropy = -sum((count / len(stripped)) * math.log2(count / len(stripped)) for count in counts.values())
    enough_text = len(stripped) >= 40
    good = (
        enough_text
        and confidence >= 0.60
        and replacement_ratio <= 0.05
        and noise_ratio <= 0.32
        and entropy >= 2.2
    )
    return {
        "ocr_quality": "good" if good else "low",
        "semantic_eligible": good,
        "replacement_ratio": round(replacement_ratio, 4),
        "noise_ratio": round(noise_ratio, 4),
        "confidence": round(confidence, 4),
        "entropy": round(entropy, 4),
    }


class OCRStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ocr_pages(
                file_sha1 TEXT NOT NULL,
                page INTEGER NOT NULL,
                dpi INTEGER NOT NULL,
                language TEXT NOT NULL,
                model_version TEXT NOT NULL,
                text TEXT NOT NULL,
                confidence REAL NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(file_sha1, page, dpi, language, model_version)
            )
            """
        )
        self.conn.commit()

    def get(self, file_sha1: str, page: int, dpi: int, language: str, model_version: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT text, confidence FROM ocr_pages
            WHERE file_sha1=? AND page=? AND dpi=? AND language=? AND model_version=?
            """,
            (file_sha1, page, dpi, language, model_version),
        ).fetchone()
        return dict(row) if row else None

    def upsert(
        self,
        file_sha1: str,
        page: int,
        dpi: int,
        language: str,
        model_version: str,
        text: str,
        confidence: float,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO ocr_pages(
                file_sha1, page, dpi, language, model_version, text, confidence, updated_at
            ) VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(file_sha1, page, dpi, language, model_version)
            DO UPDATE SET
                text=excluded.text,
                confidence=excluded.confidence,
                updated_at=CURRENT_TIMESTAMP
            """,
            (file_sha1, page, dpi, language, model_version, text, confidence),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> OCRStore:
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def discover_files(root: Path, cfg: dict[str, Any]) -> list[Path]:
    excluded = set(cfg.get("exclude", []))
    files: list[Path] = []
    for folder in cfg.get("include_dirs", []):
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            rel_parts = path.relative_to(root).parts
            if rel_parts and rel_parts[0] in excluded:
                continue
            files.append(path)
    return files


def _pdf_units(path: Path, digest: str, cfg: dict[str, Any], ocr_store: OCRStore) -> list[Unit]:
    try:
        import pymupdf
    except ImportError as exc:
        raise CockpitError("读取 PDF 需要 PyMuPDF。请执行 `pip install -e .`。") from exc

    ocr_cfg = cfg.get("ocr", {})
    units: list[Unit] = []
    document = pymupdf.open(path)
    try:
        for page_number, page in enumerate(document, 1):
            native = (page.get_text("text") or "").strip()
            native_quality = quality_metrics(native)
            text = native
            ocr_used = False
            confidence = 1.0
            warning: str | None = None

            if (not native_quality["semantic_eligible"]) and ocr_cfg.get("enabled", True):
                cached = ocr_store.get(
                    digest,
                    page_number,
                    int(ocr_cfg.get("dpi", 220)),
                    str(ocr_cfg.get("language", "chi_sim+eng")),
                    str(ocr_cfg.get("model_version", "rapidocr-v1")),
                )
                if cached is None:
                    cached = _ocr_pdf_page(page, digest, page_number, cfg, ocr_store)
                if cached and cached.get("text"):
                    ocr_text = str(cached["text"]).strip()
                    confidence = float(cached.get("confidence", 0.0))
                    if len(ocr_text) > len(native):
                        text = ocr_text
                        ocr_used = True
                else:
                    warning = "页面文字稀疏，且 OCR 扩展未安装或未产生文本。"

            metrics = quality_metrics(text, confidence if ocr_used else 1.0)
            semantic = bool(metrics["semantic_eligible"])
            if not semantic:
                warning = warning or "文本质量低，保留词法检索但不进入语义向量索引。"
            units.append(
                Unit(
                    unit=page_number,
                    unit_label=f"页{page_number}",
                    text=text,
                    ocr=ocr_used,
                    ocr_confidence=round(float(metrics["confidence"]), 4),
                    ocr_quality=str(metrics["ocr_quality"]),
                    semantic_eligible=semantic,
                    replacement_ratio=float(metrics["replacement_ratio"]),
                    noise_ratio=float(metrics["noise_ratio"]),
                    warning=warning,
                )
            )
    finally:
        document.close()
    return units


def _ocr_pdf_page(
    page: Any,
    digest: str,
    page_number: int,
    cfg: dict[str, Any],
    store: OCRStore,
) -> dict[str, Any] | None:
    global _RAPIDOCR_ENGINE
    try:
        import pymupdf
        if _RAPIDOCR_ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR

            _RAPIDOCR_ENGINE = RapidOCR()
    except ImportError:
        return None

    ocr_cfg = cfg.get("ocr", {})
    dpi = int(ocr_cfg.get("dpi", 220))
    language = str(ocr_cfg.get("language", "chi_sim+eng"))
    model_version = str(ocr_cfg.get("model_version", "rapidocr-v1"))
    scale = dpi / 72
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    with tempfile.TemporaryDirectory(prefix="acc_cockpit_ocr_") as tmp:
        image_path = Path(tmp) / f"page-{page_number}.png"
        pixmap.save(image_path)
        result, _ = _RAPIDOCR_ENGINE(str(image_path))
    if not result:
        value = {"text": "", "confidence": 0.0}
    else:
        pieces = [str(item[1]) for item in result if len(item) > 1 and item[1]]
        scores = [float(item[2]) for item in result if len(item) > 2 and item[2] is not None]
        value = {
            "text": "\n".join(pieces),
            "confidence": sum(scores) / len(scores) if scores else 0.0,
        }
    store.upsert(digest, page_number, dpi, language, model_version, value["text"], value["confidence"])
    return value


def _pptx_units(path: Path) -> list[Unit]:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise CockpitError("读取 PPTX 需要 python-pptx。请执行 `pip install -e .`。") from exc
    presentation = Presentation(str(path))
    units: list[Unit] = []
    for number, slide in enumerate(presentation.slides, 1):
        parts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = shape.text_frame.text.strip()
                if text:
                    parts.append(text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes_frame = getattr(slide.notes_slide, "notes_text_frame", None)
            notes = notes_frame.text.strip() if notes_frame is not None else ""
            if notes:
                parts.append(f"[备注] {notes}")
        text = "\n".join(parts).strip()
        metrics = quality_metrics(text)
        units.append(
            Unit(
                unit=number,
                unit_label=f"张{number}",
                text=text,
                ocr=False,
                ocr_confidence=1.0,
                ocr_quality=str(metrics["ocr_quality"]),
                semantic_eligible=bool(metrics["semantic_eligible"]),
                replacement_ratio=float(metrics["replacement_ratio"]),
                noise_ratio=float(metrics["noise_ratio"]),
                warning=None if metrics["semantic_eligible"] else "幻灯片文字不足，仅保留词法检索。",
            )
        )
    return units


def _docx_units(path: Path) -> list[Unit]:
    try:
        import docx
    except ImportError as exc:
        raise CockpitError("读取 DOCX 需要 python-docx。请执行 `pip install -e .`。") from exc
    document = docx.Document(str(path))
    parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = "\n".join(parts)
    metrics = quality_metrics(text)
    return [
        Unit(
            unit=1,
            unit_label="正文",
            text=text,
            ocr=False,
            ocr_confidence=1.0,
            ocr_quality=str(metrics["ocr_quality"]),
            semantic_eligible=bool(metrics["semantic_eligible"]),
            replacement_ratio=float(metrics["replacement_ratio"]),
            noise_ratio=float(metrics["noise_ratio"]),
            warning="DOCX 无可靠固定页码，定位到全文正文。",
        )
    ]


def _text_units(path: Path) -> list[Unit]:
    text = ""
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    metrics = quality_metrics(text)
    return [
        Unit(
            unit=1,
            unit_label="正文",
            text=text,
            ocr=False,
            ocr_confidence=1.0,
            ocr_quality=str(metrics["ocr_quality"]),
            semantic_eligible=bool(metrics["semantic_eligible"]),
            replacement_ratio=float(metrics["replacement_ratio"]),
            noise_ratio=float(metrics["noise_ratio"]),
        )
    ]


def extract_file(path: Path, digest: str, cfg: dict[str, Any], paths: Paths) -> list[Unit]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        with OCRStore(paths.ocr_db) as store:
            return _pdf_units(path, digest, cfg, store)
    if suffix == ".pptx":
        return _pptx_units(path)
    if suffix == ".docx":
        return _docx_units(path)
    return _text_units(path)


def units_from_json(values: Iterable[dict[str, Any]]) -> list[Unit]:
    return [Unit(**value) for value in values]


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
