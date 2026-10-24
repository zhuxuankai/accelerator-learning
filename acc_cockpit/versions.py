from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DATE_YYYYMMDD = re.compile(r"(?:^|[-_—－\s])(20\d{6})(?=$|[-_—－\s])")
DATE_MMDD = re.compile(r"(?:^|[-_—－\s])(\d{4})(?=$|[-_—－\s])")
REVISION = re.compile(r"(?:^|[-_—－\s])(?:v|ver|rev)(\d+)(?=$|[-_—－\s])", re.I)
REVISION_CN = re.compile(r"第\s*(\d+)\s*版")
TRAILING_NUMBER = re.compile(r"[\(（]\s*(\d+)\s*[\)）]\s*$")
TRAILING_DESCRIPTORS = re.compile(r"[-_—－\s]*(?:副本|完整|最终版?|定稿)\s*$")


@dataclass(frozen=True)
class Marker:
    year: int | None
    month: int | None
    day: int | None
    revision: int | None
    basis: str

    @property
    def sort_key(self) -> tuple[int, int, int, int]:
        return (
            self.year or 0,
            self.month or 0,
            self.day or 0,
            self.revision or 0,
        )

    @property
    def explicit(self) -> bool:
        return self.basis != "none"


@dataclass
class VersionDecision:
    rel_path: str
    version_group: str
    version_basis: str
    authoritative: bool
    search_eligible: bool
    ambiguous: bool
    duplicate_of: str | None
    warning: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _valid_date(year: int, month_text: str, day_text: str) -> tuple[int, int, int] | None:
    month, day = int(month_text), int(day_text)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return year, month, day


def parse_marker(stem: str) -> Marker:
    match = DATE_YYYYMMDD.search(stem)
    if match:
        value = match.group(1)
        date = _valid_date(int(value[:4]), value[4:6], value[6:8])
        if date:
            return Marker(*date, revision=None, basis="filename_date")

    dates = []
    for match in DATE_MMDD.finditer(stem):
        date = _valid_date(2000, match.group(1)[:2], match.group(1)[2:])
        if date:
            dates.append(date)
    if dates:
        year, month, day = dates[-1]
        return Marker(year, month, day, revision=None, basis="filename_date")

    match = REVISION.search(stem)
    if match:
        return Marker(None, None, None, revision=int(match.group(1)), basis="filename_revision")
    match = REVISION_CN.search(stem)
    if match:
        return Marker(None, None, None, revision=int(match.group(1)), basis="filename_revision")
    match = TRAILING_NUMBER.search(stem)
    if match:
        return Marker(None, None, None, revision=int(match.group(1)), basis="filename_revision")
    return Marker(None, None, None, revision=None, basis="none")


def version_group(rel_path: str) -> str:
    path = Path(rel_path)
    stem = path.stem
    for regex in (DATE_YYYYMMDD, DATE_MMDD, REVISION, REVISION_CN, TRAILING_NUMBER, TRAILING_DESCRIPTORS):
        stem = regex.sub("", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" -_—－")
    return f"{path.parent.as_posix()}/{stem}"


def _file_id(rel_path: str, sha1: str) -> str:
    return hashlib.sha1(f"{rel_path}\0{sha1}".encode()).hexdigest()[:24]


def analyze_versions(records: Iterable[dict[str, Any]]) -> dict[str, VersionDecision]:
    items = list(records)
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(version_group(item["rel_path"]), []).append(item)

    decisions: dict[str, VersionDecision] = {}
    for group, members in groups.items():
        by_hash: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            by_hash.setdefault(member["sha1"], []).append(member)

        unique: list[dict[str, Any]] = []
        for digest, duplicates in by_hash.items():
            canonical = sorted(duplicates, key=lambda x: (len(x["rel_path"]), x["rel_path"]))[0]
            canonical_path = canonical["rel_path"]
            marker = parse_marker(Path(canonical["rel_path"]).stem)
            canonical = {**canonical, "marker": marker, "sha1": digest}
            unique.append(canonical)
            for duplicate in duplicates:
                if duplicate["rel_path"] == canonical_path:
                    continue
                decisions[duplicate["rel_path"]] = VersionDecision(
                    rel_path=duplicate["rel_path"],
                    version_group=group,
                    version_basis="content_duplicate",
                    authoritative=False,
                    search_eligible=False,
                    ambiguous=False,
                    duplicate_of=canonical["rel_path"],
                    warning=f"内容与 {canonical['rel_path']} 完全相同，默认只检索一份。",
                )

        if len(unique) == 1:
            item = unique[0]
            basis = item["marker"].basis
            decisions[item["rel_path"]] = VersionDecision(
                rel_path=item["rel_path"],
                version_group=group,
                version_basis=basis,
                authoritative=True,
                search_eligible=True,
                ambiguous=False,
                duplicate_of=None,
                warning=None if basis != "none" else "只有一个同名文件；未发现显式版本标记。",
            )
            continue

        explicit = [item for item in unique if item["marker"].explicit]
        if not explicit:
            for item in unique:
                decisions[item["rel_path"]] = VersionDecision(
                    rel_path=item["rel_path"],
                    version_group=group,
                    version_basis="ambiguous",
                    authoritative=False,
                    search_eligible=True,
                    ambiguous=True,
                    duplicate_of=None,
                    warning="无法从文件名判断版本先后，默认保留全部版本并标记为歧义。",
                )
            continue

        max_key = max(item["marker"].sort_key for item in explicit)
        leaders = [item for item in explicit if item["marker"].sort_key == max_key]
        leader_path: str
        warning: str | None = None
        if len(leaders) == 1:
            leader_path = leaders[0]["rel_path"]
        else:
            leaders.sort(key=lambda x: (float(x.get("mtime", 0)), x["rel_path"]), reverse=True)
            leader_path = leaders[0]["rel_path"]
            warning = "多个文件的显式版本相同但内容不同；已用 mtime 仅作同日次级判断，请复核。"

        for item in unique:
            is_leader = item["rel_path"] == leader_path
            item_warning = warning if is_leader else None
            decisions[item["rel_path"]] = VersionDecision(
                rel_path=item["rel_path"],
                version_group=group,
                version_basis=item["marker"].basis,
                authoritative=is_leader,
                search_eligible=is_leader,
                ambiguous=False,
                duplicate_of=None,
                warning=item_warning,
            )
    return decisions


def node_document_id(rel_path: str, sha1: str, unit: int, part: int) -> str:
    return _file_id(f"{rel_path}:{unit}:{part}", sha1)
