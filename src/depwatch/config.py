import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    vault_repo: str
    vault_folder: str
    timezone: str
    tier1_base_url: str
    tier1_model: str
    tier2_model: str
    tier2_max_calls: int
    allowlist: list[str]
    github_token: str
    anthropic_api_key: str | None
    ntfy_topic: str | None
    data_dir: Path
    tier2_provider: str = "local"
    tier2_base_url: str = ""
    committer_name: str = "depwatch"
    committer_email: str = "depwatch@localhost"


def _require(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if not value:
        raise ConfigError(f"{key} is not set")
    return value


def _check_repo(name: str) -> str:
    parts = name.split("/")
    if len(parts) != 2 or not all(parts):
        raise ConfigError(f"repo {name!r} is not in owner/name form")
    return name


def load(path: Path, env: Mapping[str, str]) -> Config:
    if not path.is_file():
        raise ConfigError(f"{path} not found, copy config.example.toml to {path} and edit it")
    raw = tomllib.loads(path.read_text())
    vault = raw["vault"]
    tier1 = raw["llm"]["tier1"]
    tier2 = raw["llm"]["tier2"]
    allowlist = [_check_repo(r) for r in raw["repos"]["allowlist"]]
    _check_repo(vault["repo"])
    tier1_base_url = tier1["base_url"].rstrip("/")
    tier2_provider = tier2.get("provider", "local")
    if tier2_provider not in ("local", "anthropic"):
        raise ConfigError(f"llm.tier2 provider {tier2_provider!r} must be 'local' or 'anthropic'")
    anthropic_api_key = env.get("ANTHROPIC_API_KEY") or None
    if tier2_provider == "anthropic" and not anthropic_api_key:
        raise ConfigError("ANTHROPIC_API_KEY is not set")
    return Config(
        vault_repo=vault["repo"],
        vault_folder=vault["folder"].strip("/"),
        timezone=vault.get("timezone", "UTC"),
        tier1_base_url=tier1_base_url,
        tier1_model=tier1["model"],
        tier2_model=tier2.get("model", "claude-sonnet-5"),
        tier2_max_calls=int(tier2.get("max_calls_per_run", 10)),
        allowlist=allowlist,
        github_token=_require(env, "GITHUB_TOKEN"),
        anthropic_api_key=anthropic_api_key,
        ntfy_topic=env.get("NTFY_TOPIC") or None,
        data_dir=Path(env.get("DEPWATCH_DATA_DIR", "data")),
        tier2_provider=tier2_provider,
        tier2_base_url=tier2.get("base_url", tier1_base_url).rstrip("/"),
        committer_name=vault.get("committer_name", "depwatch"),
        committer_email=vault.get("committer_email", "depwatch@localhost"),
    )
