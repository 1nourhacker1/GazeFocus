import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Every test gets its own GazeFocus home so nothing touches %APPDATA%."""
    home = tmp_path / "gazefocus-home"
    monkeypatch.setenv("GAZEFOCUS_HOME", str(home))
    return home


@pytest.fixture(scope="session")
def qapp():
    """One offscreen QApplication for every Qt test (no windows appear on the desktop)."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
