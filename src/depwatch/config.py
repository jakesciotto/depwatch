import fnmatch
import tomllib
from dataclasses import dataclass, field
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
    osv: bool = True
    ignore_packages: list[str] = field(default_factory=list)
    ignore_repos: dict[str, list[str]] = field(default_factory=dict)
    collapse_dev: bool = True

    def ignored(self, repo: str, name: str) -> bool:
        globs = self.ignore_packages + self.ignore_repos.get(repo, [])
        return any(fnmatch.fnmatchcase(name, g) for g in globs)


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
    vault = raw.get("vault", {})
    llm = raw.get("llm", {})
    tier1, tier2 = llm.get("tier1", {}), llm.get("tier2", {})
    allowlist = [_check_repo(r) for r in raw.get("repos", {}).get("allowlist", [])]
    if not allowlist:
        raise ConfigError("repos.allowlist is empty")
    vault_repo = vault.get("repo", "")
    if vault_repo:
        _check_repo(vault_repo)
    tier1_base_url = tier1.get("base_url", "").rstrip("/")
    tier2_provider = tier2.get("provider", "local")
    if tier2_provider not in ("local", "anthropic"):
        raise ConfigError(f"llm.tier2 provider {tier2_provider!r} must be 'local' or 'anthropic'")
    ignore = raw.get("ignore", {})
    ignore_repos = {_check_repo(k): list(v.get("packages", [])) for k, v in ignore.items() if isinstance(v, dict)}
    anthropic_api_key = env.get("ANTHROPIC_API_KEY") or None
    if tier2_provider == "anthropic" and not anthropic_api_key:
        raise ConfigError("ANTHROPIC_API_KEY is not set")
    return Config(
        vault_repo=vault_repo,
        vault_folder=vault.get("folder", "dependencies").strip("/"),
        timezone=vault.get("timezone", "UTC"),
        tier1_base_url=tier1_base_url,
        tier1_model=tier1.get("model", ""),
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
        osv=bool(raw.get("advisories", {}).get("osv", True)),
        ignore_packages=list(ignore.get("packages", [])),
        ignore_repos=ignore_repos,
        collapse_dev=bool(raw.get("releases", {}).get("collapse_dev", True)),
    )
