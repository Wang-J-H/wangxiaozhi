import sys


def test_import_xiaozhi_does_not_eagerly_import_knowledge(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    sys.modules.pop("xiaozhi", None)
    sys.modules.pop("xiaozhi.knowledge", None)

    import xiaozhi

    assert xiaozhi.get_version() == xiaozhi.__version__
    assert "xiaozhi.knowledge" not in sys.modules
