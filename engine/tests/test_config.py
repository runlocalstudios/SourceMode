from sourcemode.config import load_config


def test_defaults_load():
    cfg = load_config(env={})
    assert cfg["comfyui"]["host"] == "127.0.0.1"
    assert cfg["comfyui"]["port"] == 8188
    assert cfg["gates"]["identity_enabled"] is True


def test_alias_env_overrides():
    cfg = load_config(env={
        "SOURCEMODE_COMFYUI_HOST": "10.0.0.5",
        "SOURCEMODE_COMFYUI_PORT": "9999",
        "SOURCEMODE_IDENTITY_GATE_ENABLED": "false",
    })
    assert cfg["comfyui"]["host"] == "10.0.0.5"
    assert cfg["comfyui"]["port"] == 9999  # coerced to int
    assert cfg["gates"]["identity_enabled"] is False


def test_generic_section_key_override():
    cfg = load_config(env={"SOURCEMODE_VIDEO_FPS": "24"})
    assert cfg["video"]["fps"] == 24


def test_irrelevant_env_ignored():
    cfg = load_config(env={"SOURCEMODE_NOSUCH_THING": "x", "PATH": "y"})
    assert "nosuch" not in cfg
