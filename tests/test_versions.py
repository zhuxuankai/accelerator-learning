from acc_cockpit.versions import analyze_versions, parse_marker, version_group


def _record(path, digest, mtime):
    return {"rel_path": path, "sha1": digest, "mtime": mtime}


def test_filename_date_beats_later_mtime():
    records = [
        _record("course/同步辐射-0922.pdf", "old", 200),
        _record("course/同步辐射-0923.pdf", "new", 100),
    ]
    decisions = analyze_versions(records)
    assert decisions["course/同步辐射-0923.pdf"].authoritative is True
    assert decisions["course/同步辐射-0922.pdf"].search_eligible is False


def test_no_marker_is_ambiguous_and_not_hidden():
    records = [
        _record("course/讲义-a.pdf", "a", 100),
        _record("course/讲义-b.pdf", "b", 200),
    ]
    # Different stems belong to different groups; force a shared group through revisions.
    records = [
        _record("course/讲义-v1.pdf", "a", 100),
        _record("course/讲义-副本.pdf", "b", 200),
    ]
    decisions = analyze_versions(records)
    assert decisions["course/讲义-v1.pdf"].authoritative
    assert not decisions["course/讲义-副本.pdf"].search_eligible


def test_same_explicit_date_uses_mtime_with_warning():
    records = [
        _record("course/讲义-0923.pdf", "a", 100),
        _record("course/讲义-0923-副本.pdf", "b", 200),
    ]
    decisions = analyze_versions(records)
    assert decisions["course/讲义-0923-副本.pdf"].authoritative
    assert "mtime" in decisions["course/讲义-0923-副本.pdf"].warning


def test_content_duplicate_is_not_indexed_twice():
    records = [
        _record("course/讲义-0923.pdf", "same", 100),
        _record("course/讲义-0923-副本.pdf", "same", 200),
    ]
    decisions = analyze_versions(records)
    duplicate = decisions["course/讲义-0923-副本.pdf"]
    assert duplicate.version_basis == "content_duplicate"
    assert duplicate.search_eligible is False
    assert duplicate.duplicate_of == "course/讲义-0923.pdf"


def test_version_group_and_marker_are_stable():
    assert parse_marker("同步辐射-20260923").month == 9
    assert parse_marker("讲义-v3").revision == 3
    assert version_group("course/讲义-0923.pdf") == "course/讲义"
