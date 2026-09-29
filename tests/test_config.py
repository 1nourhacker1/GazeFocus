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
