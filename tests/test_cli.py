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
