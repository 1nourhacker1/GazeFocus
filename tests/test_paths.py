import sys

from gazefocus import paths


def test_from_source_the_model_is_in_the_repo():
    assert paths.model_path() == paths.repo_root() / "models" / "face_landmarker.task"


def test_inside_a_standalone_build_the_model_is_in_the_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)  # what PyInstaller sets
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.model_path() == tmp_path / "models" / "face_landmarker.task"
