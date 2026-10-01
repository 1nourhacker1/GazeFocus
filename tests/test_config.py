import os

from gazefocus.config import Config, ConfigWatcher, default_toml, load_config, write_default_config


def write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_file_gives_defaults(tmp_path):
    cfg, warns = load_config(tmp_path / "nope.toml")
    assert cfg == Config() and warns == []


def test_partial_override_and_int_to_float(tmp_path):
    p = write(tmp_path / "c.toml", "[decider]\ndwell_ms = 700\n[classifier]\nema_alpha = 1\n")
    cfg, warns = load_config(p)
    assert warns == []
    assert cfg.decider.dwell_ms == 700 and cfg.decider.typing_freeze_ms == 1500
    assert cfg.classifier.ema_alpha == 1.0 and isinstance(cfg.classifier.ema_alpha, float)


def test_invalid_values_keep_defaults_and_warn(tmp_path):
    p = write(
        tmp_path / "c.toml",
        '[decider]\ndwell_ms = -5\ntyping_freeze_ms = true\n[classifier]\nema_alpha = 0\n[camera]\nfps = "fast"\n',
    )
    cfg, warns = load_config(p)
    assert cfg == Config()
    assert len(warns) == 4
    assert any("[decider].dwell_ms" in w and "default 500" in w for w in warns)


def test_unknown_section_and_key_warn(tmp_path):
    p = write(tmp_path / "c.toml", "[decider]\nbogus = 1\n[extras]\nx = 1\n")
    cfg, warns = load_config(p)
    assert cfg == Config()
    assert any("[decider].bogus" in w for w in warns) and any("[extras]" in w for w in warns)


def test_invalid_toml_gives_defaults(tmp_path):
    cfg, warns = load_config(write(tmp_path / "c.toml", "[decider\ndwell_ms = 1"))
    assert cfg == Config() and len(warns) == 1 and "not valid TOML" in warns[0]


def test_default_toml_round_trips(tmp_path):
    p = tmp_path / "c.toml"
    assert write_default_config(p) is True
    assert write_default_config(p) is False  # never overwrites
    cfg, warns = load_config(p)
    assert cfg == Config() and warns == []
    assert "dwell_ms = 500" in default_toml() and 'pause = "Ctrl+Alt+G"' in default_toml()


def test_watcher_reloads_on_change_and_delete(tmp_path):
    p = write(tmp_path / "c.toml", "[decider]\ndwell_ms = 600\n")
    seen = []
    w = ConfigWatcher(p, lambda cfg, warns: seen.append(cfg.decider.dwell_ms))
    assert w.poll() is False
    write(p, "[decider]\ndwell_ms = 800\n")
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert w.poll() is True and seen == [800]
    p.unlink()
    assert w.poll() is True and seen == [800, 500]


def test_unreadable_config_gives_defaults(tmp_path):
    """Plan 1 review: an editor's delete-and-rename save can make the file briefly unreadable."""
    folder = tmp_path / "config.toml"
    folder.mkdir()  # reading a directory raises OSError
    cfg, warns = load_config(folder)
    assert cfg == Config() and len(warns) == 1 and "could not read" in warns[0]


def test_dock_defaults_are_the_bigger_pill_with_the_lens():
    d = Config().dock
    assert (d.enabled, d.monitor, d.scale, d.refraction) == (True, "primary", 2.625, True)


def test_booleans_are_written_as_toml_booleans(tmp_path):
    text = default_toml()
    assert "enabled = true" in text and "refraction = true" in text and "scale = 2.625" in text
    p = tmp_path / "config.toml"
    p.write_text(text.replace("refraction = true", "refraction = false"), encoding="utf-8")
    cfg, warns = load_config(p)
    assert cfg.dock.refraction is False and warns == []


def test_a_non_boolean_dock_switch_falls_back_with_a_warning(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[dock]\nenabled = "yes"\n', encoding="utf-8")
    cfg, warns = load_config(p)
    assert cfg.dock.enabled is True and any("true or false" in w for w in warns)


def test_the_old_name_of_the_face_lost_margin_still_works(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[classifier]\nface_lost_lg_margin = -2.0\n", encoding="utf-8")
    cfg, warnings = load_config(p)
    assert warnings == [] and cfg.classifier.face_lost_external_margin == -2.0
