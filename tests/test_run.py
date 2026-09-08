import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from depwatch import run
from depwatch.config import Config
from depwatch.github import Alert
from depwatch.judge import Tier1, Tier2
from depwatch.registry import RegistryInfo
from depwatch.repos import Repos
from depwatch.state import State
from depwatch.vault import Vault, VaultError
from tests.conftest import git
from tests.test_judge import FakeAnthropic, FakeParsed

TZ = timezone(timedelta(hours=-4))


class FakeRegistry:
    def __init__(self, table): self.table, self.skipped = table, 0
    def latest(self, name, eco): return self.table.get((eco, name))


class FakeGitHub:
    def __init__(self, alerts=None, fail_for=()): self.alerts, self.fail_for = alerts or {}, fail_for
    def release_notes(self, repo, after, upto): return f"notes {upto}", f"https://github.com/{repo}/releases/tag/v{upto}"
    def open_alerts(self, repo):
        if repo in self.fail_for: raise RuntimeError("GraphQL error")
        return self.alerts.get(repo, [])


class Notes:
    def __init__(self): self.msgs = []
    def failure(self, text): self.msgs.append(text)


def make_repo(tmp_path: Path, name: str, deps: dict) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    (repo / "package.json").write_text(json.dumps({"dependencies": deps}))
    (repo / "a.ts").write_text("import 'hono'\n")
    git("add", "-A", cwd=repo); git("commit", "-q", "-m", "init", cwd=repo)
    bare = tmp_path / f"{name}.git"
    git("init", "-q", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    git("remote", "add", "origin", str(bare), cwd=repo)
    git("push", "-q", "-u", "origin", "main", cwd=repo)
    return repo


@pytest.fixture
def services(tmp_path: Path):
    make_repo(tmp_path, "duels", {"hono": "4.6.1", "zod": "3.23.0"})
    vault_src = make_repo(tmp_path, "obsidian", {})
    cfg = Config(vault_repo="obsidian", vault_folder="resources/dependencies", timezone="America/New_York",
                 tier1_base_url="http://llm/v1", tier1_model="chat", tier2_model="claude-sonnet-5", tier2_max_calls=10,
                 allowlist=["duels"], github_token="t", anthropic_api_key="k", ntfy_topic="n", data_dir=tmp_path / "data")
    repos = Repos(cfg.data_dir, {}, remote_base=str(tmp_path) + "/")
    t1 = Tier1(httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"summary": "s", "risk": "low"}'}}]}))),
        cfg.tier1_base_url, cfg.tier1_model)
    t2 = Tier2(FakeAnthropic(FakeParsed("breaks a.ts:1", True)), cfg.tier2_model, cfg.tier2_max_calls)
    reg = FakeRegistry({("npm", "hono"): RegistryInfo("5.0.0", "honojs/hono"), ("npm", "zod"): RegistryInfo("3.23.1", None)})
    gh = FakeGitHub(alerts={"duels": [Alert("GHSA-1", "high", "hono", "npm", "< 4.6.2", "4.6.2", "S", "D",
                                             "https://github.com/advisories/GHSA-1", "package.json", "2026-09-01T00:00:00Z")]})
    s = run.Services(config=cfg, state=State(cfg.data_dir / "depwatch.db"), repos=repos, registry=reg, github=gh,
                     tier1=t1, tier2=t2, vault=Vault(repos, "obsidian", "resources/dependencies"), notifier=Notes(),
                     now=lambda: datetime(2026, 9, 14, 7, 0, tzinfo=TZ))
    return s, vault_src


def test_digest_publishes_and_records_state(services):
    s, vault_src = services
    text = run.digest(s, dry_run=False)
    git("pull", "-q", cwd=vault_src)
    note = (vault_src / "resources/dependencies/2026-W38.md").read_text()
    assert note == text
    assert "## Advisories" in note and "GHSA-1" in note
    assert "[hono 4.6.1 -> 5.0.0]" in note and "Breakage: breaks a.ts:1" in note and "[tier:: backlog]" in note
    assert "Patches: zod (1)." in note
    assert s.state.head("duels")
    assert s.state.release_seen("duels", "hono", "npm", "5.0.0")
    assert s.state.advisory_seen("duels", "https://github.com/advisories/GHSA-1")
    second = run.digest(s, dry_run=True)
    assert "No changes this week." in second


def test_dry_run_publishes_nothing(services):
    s, vault_src = services
    text = run.digest(s, dry_run=True)
    assert "GHSA-1" in text
    git("pull", "-q", cwd=vault_src)
    assert not (vault_src / "resources/dependencies").exists()
    assert s.state.head("duels") is None


def test_repo_error_is_reported_not_fatal(services):
    s, _ = services
    s.config = run.replace(s.config, allowlist=["duels", "missing"])
    text = run.digest(s, dry_run=True)
    assert "## missing" in text and "fetch failed" in text


def test_advisory_run_appends_section(services):
    s, vault_src = services
    run.digest(s, dry_run=False)
    s.github.alerts["duels"].append(Alert("GHSA-2", "critical", "zod", "npm", "< 3.24", "3.24.0", "S2", "D2",
                                          "https://github.com/advisories/GHSA-2", "package.json", "2026-09-15T00:00:00Z"))
    s.now = lambda: datetime(2026, 9, 16, 7, 0, tzinfo=TZ)
    run.advisory(s, dry_run=False)
    git("pull", "-q", cwd=vault_src)
    note = (vault_src / "resources/dependencies/2026-W38.md").read_text()
    assert note.count("## Advisories") == 1
    assert "## Advisory 2026-09-16" in note and "GHSA-2" in note
    assert note.index("## Advisory 2026-09-16") > note.index("## duels")


def test_advisory_run_with_nothing_new_publishes_nothing(services):
    s, vault_src = services
    run.digest(s, dry_run=False)
    assert run.advisory(s, dry_run=False) == ""
    git("pull", "-q", cwd=vault_src)
    assert "## Advisory" not in (vault_src / "resources/dependencies/2026-W38.md").read_text()


def test_publish_failure_notifies_and_keeps_state(services, monkeypatch):
    s, _ = services
    def boom(*a, **k): raise VaultError("push rejected after 3 attempts")
    monkeypatch.setattr(s.vault, "publish", boom)
    with pytest.raises(VaultError):
        run.digest(s, dry_run=False)
    assert s.notifier.msgs and "push rejected" in s.notifier.msgs[0]
    assert s.state.head("duels") is None


def _bump_hono(tmp_path: Path) -> None:
    duels = tmp_path / "duels"
    (duels / "package.json").write_text(json.dumps({"dependencies": {"hono": "4.6.2", "zod": "3.23.0"}}))
    git("add", "-A", cwd=duels)
    git("commit", "-q", "-m", "bump hono", cwd=duels)
    git("push", "-q", cwd=duels)


def test_advisory_publish_does_not_move_landed_watermark(services, tmp_path):
    s, _ = services
    run.digest(s, dry_run=False)
    _bump_hono(tmp_path)
    s.github.alerts["duels"].append(Alert("GHSA-2", "critical", "zod", "npm", "< 3.24", "3.24.0", "S2", "D2",
                                          "https://github.com/advisories/GHSA-2", "package.json", "2026-09-15T00:00:00Z"))
    s.now = lambda: datetime(2026, 9, 16, 7, 0, tzinfo=TZ)
    run.advisory(s, dry_run=False)
    text = run.digest(s, dry_run=True)
    assert "[hono 4.6.1 -> 4.6.2]" in text


def test_digest_rerun_publish_returns_actual_published_text(services, tmp_path):
    s, vault_src = services
    run.digest(s, dry_run=False)
    _bump_hono(tmp_path)
    text = run.digest(s, dry_run=False)
    git("pull", "-q", cwd=vault_src)
    note = (vault_src / "resources/dependencies/2026-W38.md").read_text()
    assert text == note
    assert "## Digest re-run" in text


def test_feed_failure_does_not_move_head(services, monkeypatch):
    s, _ = services
    def boom(*a, **k): raise RuntimeError("git log failed")
    monkeypatch.setattr(run.landed, "collect", boom)
    text = run.digest(s, dry_run=False)
    assert "fetch failed" in text
    assert s.state.head("duels") is None
