import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Every test gets its own GazeFocus home so nothing touches %APPDATA%."""
    home = tmp_path / "gazefocus-home"
    monkeypatch.setenv("GAZEFOCUS_HOME", str(home))
    return home
