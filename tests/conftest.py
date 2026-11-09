import pytest


@pytest.fixture(autouse=True)
def isolated_user_dirs(tmp_path, monkeypatch):
    """Never touch the real ~/Library/Caches or ~/.config during tests."""
    monkeypatch.setenv("CSK_CACHE_DIR", str(tmp_path / "cache"))
    config = tmp_path / "config.toml"
    config.write_text(f'save_dir = "{tmp_path / "saved"}"\n')
    monkeypatch.setenv("CSK_CONFIG", str(config))
    return tmp_path
