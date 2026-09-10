from pathlib import Path

import pytest

from depwatch import config


SAMPLE = """
[vault]
repo = "acme/obsidian"
folder = "resources/dependencies"
timezone = "America/New_York"

[llm.tier1]
base_url = "http://localhost:8080/v1"
model = "chat"

[llm.tier2]
model = "claude-sonnet-5"
max_calls_per_run = 10

[repos]
allowlist = ["acme/a", "acme/b"]
"""

ENV = {"GITHUB_TOKEN": "gh", "ANTHROPIC_API_KEY": "ak", "NTFY_TOPIC": "t", "DEPWATCH_DATA_DIR": "/data"}


def test_load_reads_toml_and_env(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE)
    cfg = config.load(p, ENV)
    assert cfg.vault_repo == "acme/obsidian"
    assert cfg.vault_folder == "resources/dependencies"
    assert cfg.timezone == "America/New_York"
    assert cfg.tier1_base_url == "http://localhost:8080/v1"
    assert cfg.tier1_model == "chat"
    assert cfg.tier2_model == "claude-sonnet-5"
    assert cfg.tier2_max_calls == 10
    assert cfg.allowlist == ["acme/a", "acme/b"]
    assert cfg.github_token == "gh"
    assert cfg.anthropic_api_key == "ak"
    assert cfg.ntfy_topic == "t"
    assert cfg.data_dir == Path("/data")


def test_missing_github_token_raises(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE)
    env = dict(ENV)
    del env["GITHUB_TOKEN"]
    with pytest.raises(config.ConfigError, match="GITHUB_TOKEN"):
        config.load(p, env)


def test_data_dir_defaults_to_local_data(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE)
    env = {k: v for k, v in ENV.items() if k != "DEPWATCH_DATA_DIR"}
    cfg = config.load(p, env)
    assert cfg.data_dir == Path("data")


def test_repo_not_owner_slash_name_raises(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE.replace('"acme/b"', '"b"'))
    with pytest.raises(config.ConfigError, match="owner/name"):
        config.load(p, ENV)


def test_tier2_provider_defaults_to_local_with_tier1_base_url(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE)
    cfg = config.load(p, ENV)
    assert cfg.tier2_provider == "local"
    assert cfg.tier2_base_url == cfg.tier1_base_url


def test_tier2_provider_anthropic_with_key_loads(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE.replace('[llm.tier2]', '[llm.tier2]\nprovider = "anthropic"'))
    cfg = config.load(p, ENV)
    assert cfg.tier2_provider == "anthropic"


def test_tier2_provider_anthropic_without_key_raises(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE.replace('[llm.tier2]', '[llm.tier2]\nprovider = "anthropic"'))
    env = dict(ENV)
    del env["ANTHROPIC_API_KEY"]
    with pytest.raises(config.ConfigError, match="ANTHROPIC_API_KEY"):
        config.load(p, env)


def test_tier2_provider_bogus_raises(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE.replace('[llm.tier2]', '[llm.tier2]\nprovider = "bogus"'))
    with pytest.raises(config.ConfigError, match="provider"):
        config.load(p, ENV)


def test_missing_config_file_raises(tmp_path: Path):
    with pytest.raises(config.ConfigError, match="not found"):
        config.load(tmp_path / "config.toml", ENV)


def test_timezone_and_committer_defaults(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE.replace('timezone = "America/New_York"\n', ""))
    cfg = config.load(p, ENV)
    assert cfg.timezone == "UTC"
    assert cfg.committer_name == "depwatch"
    assert cfg.committer_email == "depwatch@localhost"


def test_committer_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE.replace("[vault]\n", '[vault]\ncommitter_name = "bot"\ncommitter_email = "bot@example.com"\n'))
    cfg = config.load(p, ENV)
    assert cfg.committer_name == "bot"
    assert cfg.committer_email == "bot@example.com"


def test_minimal_config_loads_without_vault_or_llm(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[repos]\nallowlist = ["acme/a"]\n')
    cfg = config.load(p, {"GITHUB_TOKEN": "gh"})
    assert cfg.allowlist == ["acme/a"]
    assert cfg.vault_repo == "" and cfg.vault_folder == "dependencies"
    assert cfg.tier1_base_url == "" and cfg.tier2_base_url == ""


def test_empty_allowlist_raises(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text("[repos]\nallowlist = []\n")
    with pytest.raises(config.ConfigError, match="allowlist"):
        config.load(p, ENV)


def test_advisories_osv_defaults_on_and_reads_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(SAMPLE)
    assert config.load(p, ENV).osv is True
    p.write_text(SAMPLE + "\n[advisories]\nosv = false\n")
    assert config.load(p, ENV).osv is False
