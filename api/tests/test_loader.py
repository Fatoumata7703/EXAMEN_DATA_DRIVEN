import pytest

from api.services import model_loader


def test_sha_verification_rejects_tampering(model_root, monkeypatch):
    model_loader.load_registry.cache_clear()
    original = model_loader.sha256

    def tampered(path):
        if path.name == "metadata.json" and path.parent.name == "api_bundle":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(model_loader, "sha256", tampered)
    with pytest.raises(ValueError, match="SHA-256"):
        model_loader.load_registry(model_root)
    model_loader.load_registry.cache_clear()


def test_invalidated_model_is_refused(model_root, monkeypatch):
    model_loader.load_registry.cache_clear()
    original = model_loader._read_json

    def select_invalidated(path):
        value = original(path)
        if path.name == "FINAL_STATUS.json":
            value["status"]["pricing_operational_volume_model"] = "LightGBM_calibre"
        return value

    monkeypatch.setattr(model_loader, "_read_json", select_invalidated)
    with pytest.raises(RuntimeError, match="invalidé"):
        model_loader.load_registry(model_root)
    model_loader.load_registry.cache_clear()
