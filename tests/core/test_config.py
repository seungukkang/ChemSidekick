from pathlib import Path

import pytest

from chemsidekick.core.config import Config, ConfigError, load_config


def test_missing_file_gives_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg == Config()
    assert cfg.recent_limit == 50
    assert cfg.save_dir == Path.home() / "Documents" / "ChemSidekick"


def test_values_and_tilde_expansion(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text(
        'save_dir = "~/csk"\n'
        "recent_limit = 10\n"
        "[programs.xtb]\n"
        'path = "~/bin/xtb"\n'
        "[programs.crest]\n"
        'conda_env = "csk-ext"\n'
    )
    cfg = load_config(f)
    assert cfg.save_dir == Path.home() / "csk"
    assert cfg.recent_limit == 10
    assert cfg.programs["xtb"].path == Path.home() / "bin" / "xtb"
    assert cfg.programs["crest"].conda_env == "csk-ext"


@pytest.mark.parametrize(
    "content",
    [
        "recent_limit = = 3",  # broken TOML
        "recent_limit = 0",  # out of range
        "recnt_limit = 5",  # typo in a key
    ],
)
def test_bad_config_raises(tmp_path, content):
    f = tmp_path / "config.toml"
    f.write_text(content)
    with pytest.raises(ConfigError, match=str(f)):
        load_config(f)
