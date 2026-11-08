from acc_cockpit import embedding


def test_model_cache_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(embedding, "model_cache_dir", lambda: tmp_path)
    model = "org/model"
    assert embedding.model_cache_exists(model) is False
    snapshot = tmp_path / "models--org--model" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    assert embedding.model_cache_exists(model) is True


def test_model_download_requires_config_or_explicit_env(monkeypatch):
    monkeypatch.delenv("ACCKB_ALLOW_MODEL_DOWNLOAD", raising=False)
    assert embedding.model_download_allowed({}) is False
    assert embedding.model_download_allowed({"model": {"allow_download": True}}) is True
    monkeypatch.setenv("ACCKB_ALLOW_MODEL_DOWNLOAD", "1")
    assert embedding.model_download_allowed({}) is True
