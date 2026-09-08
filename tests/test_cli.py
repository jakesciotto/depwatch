from pathlib import Path

from depwatch import cli, config, run

TOML = """
[vault]
repo = "acme/obsidian"
folder = "resources/dependencies"
timezone = "America/New_York"

[llm.tier1]
base_url = "http://llm/v1"
model = "chat"

[llm.tier2]
model = "claude-sonnet-5"
max_calls_per_run = 10

[repos]
allowlist = ["acme/duels"]
"""


def _write_config(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(TOML)
    return cfg_path


def test_main_digest_writes_stub_output(tmp_path, monkeypatch, capsys):
    cfg_path = _write_config(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("DEPWATCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(run, "digest", lambda s, dry_run: "x")
    code = cli.main(["digest", "--dry-run", "--config", str(cfg_path)])
    assert code == 0
    assert capsys.readouterr().out == "x"


def test_build_scheduler_jobs_and_timezone(tmp_path, monkeypatch):
    cfg_path = _write_config(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    cfg = config.load(cfg_path, {"GITHUB_TOKEN": "t"})
    sched = cli._build_scheduler(cfg, str(cfg_path))
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"digest", "advisory"}
    for job in jobs.values():
        assert str(job.trigger.timezone) == cfg.timezone
    digest_dow = next(f for f in jobs["digest"].trigger.fields if f.name == "day_of_week")
    advisory_dow = next(f for f in jobs["advisory"].trigger.fields if f.name == "day_of_week")
    assert str(digest_dow) == "mon"
    assert str(advisory_dow) == "tue-sun"


class RecordingNotifier:
    def __init__(self): self.msgs = []
    def failure(self, text): self.msgs.append(text)


class StubServices:
    def __init__(self): self.notifier, self.closed = RecordingNotifier(), False
    def close(self): self.closed = True


def test_guarded_job_notifies_on_failure(monkeypatch):
    s = StubServices()
    monkeypatch.setattr(run, "build_services", lambda cfg: s)
    monkeypatch.setattr(config, "load", lambda path, env: None)
    def boom(services, dry_run): raise ValueError("boom")
    boom.__name__ = "digest"
    cli._guarded(boom, "config.toml")()
    assert s.closed
    assert len(s.notifier.msgs) == 1
    assert "ValueError" in s.notifier.msgs[0] and "boom" in s.notifier.msgs[0]


def test_guarded_job_notifies_when_services_fail(monkeypatch):
    msgs = []
    def build(cfg): raise RuntimeError("no config")
    monkeypatch.setattr(run, "build_services", build)
    monkeypatch.setattr(config, "load", lambda path, env: None)
    monkeypatch.setattr(cli.Notifier, "failure", lambda self, text: msgs.append(text))
    cli._guarded(run.digest, "config.toml")()
    assert msgs and "RuntimeError" in msgs[0] and "no config" in msgs[0]
