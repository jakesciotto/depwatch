import logging
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import anthropic
import httpx

from . import advisories, judge, landed, note, releases
from .config import Config
from .github import GitHub
from .models import Finding
from .notify import Notifier
from .registry import Registry
from .repos import RepoError, Repos
from .state import State
from .vault import Vault, VaultError

log = logging.getLogger("depwatch")
__all__ = ["Services", "build_services", "digest", "advisory", "replace"]


@dataclass
class Services:
    config: Config
    state: State
    repos: Repos
    registry: Registry
    github: GitHub
    tier1: judge.Tier1
    tier2: judge.Tier2
    vault: Vault
    notifier: Notifier
    now: Callable[[], datetime]


def build_services(cfg: Config) -> Services:
    http = httpx.Client(headers={"User-Agent": "depwatch"})
    gh = GitHub(http, cfg.github_token, cfg.data_dir)
    repos = Repos(cfg.data_dir, gh.git_env())
    tz = ZoneInfo(cfg.timezone)
    return Services(
        config=cfg, state=State(cfg.data_dir / "depwatch.db"), repos=repos, registry=Registry(http), github=gh,
        tier1=judge.Tier1(http, cfg.tier1_base_url, cfg.tier1_model),
        tier2=judge.Tier2(anthropic.Anthropic(api_key=cfg.anthropic_api_key), cfg.tier2_model, cfg.tier2_max_calls),
        vault=Vault(repos, cfg.vault_repo, cfg.vault_folder, {}), notifier=Notifier(http, cfg.ntfy_topic), now=lambda: datetime.now(tz),
    )


@dataclass
class Collected:
    findings: list[Finding]
    heads: dict[str, str]
    checkouts: dict[str, Path]
    errors: dict[str, str]


def _collect(s: Services, feeds: tuple[str, ...]) -> Collected:
    c = Collected([], {}, {}, {})
    for repo in s.config.allowlist:
        try:
            path = s.repos.sync(repo)
            head = s.repos.head(path)
            c.checkouts[repo], c.heads[repo] = path, head
            if "landed" in feeds:
                c.findings += landed.collect(repo, path, s.repos, s.state.head(repo), head)
            if "releases" in feeds:
                c.findings += releases.collect(repo, path, s.registry, s.github, s.state)
            if "advisories" in feeds:
                c.findings += advisories.collect(repo, s.github, s.state)
        except (RepoError, RuntimeError, httpx.HTTPError) as e:
            log.warning("repo %s: %s", repo, e)
            c.errors[repo] = str(e)
    return c


def _finish(s: Services, c: Collected, kind: str, rel_path: str, build, message: str, dry_run: bool, text: str) -> str:
    if dry_run:
        return text
    try:
        s.vault.publish(rel_path, build, message)
    except (VaultError, RepoError) as e:
        s.notifier.failure(f"{kind} run: {e}")
        s.state.record_run(kind, "failed", rel_path, len(c.findings))
        s.state.commit()
        raise
    for repo, head in c.heads.items():
        s.state.set_head(repo, head)
    s.state.mark_releases(c.findings)
    s.state.mark_advisories(c.findings)
    s.state.record_run(kind, "ok", rel_path, len(c.findings))
    s.state.commit()
    return text


def digest(s: Services, dry_run: bool) -> str:
    now = s.now()
    week = note.week_id(now.date())
    rel_path = note.note_path(s.config.vault_folder, now.date())
    c = _collect(s, ("landed", "releases", "advisories"))
    report = judge.run(c.findings, c.checkouts.get, s.tier1, s.tier2)
    skipped = s.registry.skipped
    repos_n = len(s.config.allowlist)
    fresh = note.render_digest(week, now, repos_n, c.findings, report, skipped, c.errors)

    def build(existing: str | None) -> str:
        if existing is None:
            return fresh
        return existing.rstrip("\n") + "\n\n" + note.digest_rerun_section(now, repos_n, c.findings, report, skipped, c.errors)

    return _finish(s, c, "digest", rel_path, build, f"depwatch: {week} digest", dry_run, fresh)


def advisory(s: Services, dry_run: bool) -> str:
    now = s.now()
    week = note.week_id(now.date())
    rel_path = note.note_path(s.config.vault_folder, now.date())
    c = _collect(s, ("advisories",))
    if not c.findings and not c.errors:
        s.state.record_run("advisory", "ok", None, 0)
        s.state.commit()
        return ""
    report = judge.run(c.findings, c.checkouts.get, s.tier1, s.tier2)
    section = note.render_advisory_section(now.date(), c.findings, report)

    def build(existing: str | None) -> str:
        if existing is None:
            head = note.render_frontmatter(week, now, len(s.config.allowlist), c.findings, s.registry.skipped)
            return head + f"\n# Dependencies {week}\n\n" + section
        return existing.rstrip("\n") + "\n\n" + section

    return _finish(s, c, "advisory", rel_path, build, f"depwatch: {week} advisory", dry_run, section)
