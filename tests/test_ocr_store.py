from acc_cockpit.extract import OCRStore, quality_metrics


def test_ocr_cache_upsert_is_idempotent(tmp_path):
    store = OCRStore(tmp_path / "ocr.sqlite")
    for _ in range(5):
        store.upsert("sha", 1, 220, "chi_sim+eng", "rapidocr-v1", "第一版", 0.8)
    count = store.conn.execute("SELECT COUNT(*) FROM ocr_pages").fetchone()[0]
    assert count == 1
    store.upsert("sha", 1, 220, "chi_sim+eng", "rapidocr-v1", "更新版", 0.9)
    row = store.get("sha", 1, 220, "chi_sim+eng", "rapidocr-v1")
    assert row == {"text": "更新版", "confidence": 0.9}
    store.close()


def test_low_quality_ocr_is_excluded_from_semantic_index():
    metrics = quality_metrics("(cid:2) /\\|=^{} ????", confidence=0.3)
    assert metrics["semantic_eligible"] is False
    assert metrics["ocr_quality"] == "low"
