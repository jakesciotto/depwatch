from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from depwatch import note
from depwatch.judge import JudgeReport
from depwatch.models import Finding

TZ = timezone(timedelta(hours=-4))
GEN = datetime(2026, 9, 14, 7, 0, tzinfo=TZ)
OK = JudgeReport(True, True, 0)


def F(**kw):
    base = dict(kind="release", repo="acme/easton-duels", package="p", ecosystem="npm", current="1", target="2",
                severity="minor", source_url="u", raw="")
    base.update(kw)
    return Finding(**base)


def digest_findings():
    return [
        F(kind="advisory", package="hono", current="< 4.6.2", target="4.6.2", severity="high",
          source_url="https://github.com/advisories/GHSA-aaaa-bbbb-cccc", summary="Path traversal in static middleware.",
          breakage="server/src/app.ts:12 mounts the affected middleware.", actionable=True),
        F(kind="landed", package="drizzle-orm", current="0.36.1", target="0.38.0", severity="minor",
          source_url="https://github.com/acme/easton-duels/commit/a1b2c3d4e5f6", commit="a1b2c3d4e5f6",
          commit_date="2026-09-10T09:00:00-04:00", summary="Adds relational query v2."),
        F(kind="landed", package="left-pad", current=None, target="1.3.0", severity="minor",
          source_url="https://github.com/acme/easton-duels/commit/b2c3d4e5f6a7", commit="b2c3d4e5f6a7",
          commit_date="2026-09-11T09:00:00-04:00"),
        F(package="vitest", current="3.2.0", target="4.0.0", severity="major",
          source_url="https://github.com/vitest-dev/vitest/releases/tag/v4.0.0", summary="Drops the vi.mocked overload.",
          breakage="three test files use the removed overload.", actionable=True, import_sites=[("t.ts", 1, "x")]),
        F(package="react-router", current="7.1.0", target="7.2.0", severity="minor",
          source_url="https://github.com/remix-run/react-router/releases/tag/v7.2.0", summary="Adds data strategies."),
        F(package="@types/node", current="22.0.0", target="22.0.1", severity="patch"),
        F(package="typescript", current="5.6.3", target="5.6.4", severity="patch"),
        F(repo="acme/portfolio", package="next", current="16.2.6", target="17.0.0", severity="major",
          source_url="https://github.com/vercel/next.js/releases/tag/v17.0.0"),
    ]


def test_week_id_and_path():
    assert note.week_id(date(2026, 9, 14)) == "2026-W38"
    assert note.week_id(date(2026, 9, 8)) == "2026-W37"
    assert note.week_id(date(2027, 1, 1)) == "2026-W53"
    assert note.note_path("resources/dependencies", date(2026, 9, 8)) == "resources/dependencies/2026-W37.md"


def test_render_digest_matches_golden(fixtures: Path):
    text = note.render_digest("2026-W37", GEN, 12, digest_findings(), OK, skipped=1,
                              repo_errors={"acme/recall": "git fetch failed: could not read from remote"})
    assert text == (fixtures / "notes/digest.md").read_text()


def test_render_empty_digest(fixtures: Path):
    assert note.render_digest("2026-W37", GEN, 12, [], OK, 0, {}) == (fixtures / "notes/empty.md").read_text()


def test_render_advisory_section(fixtures: Path):
    fs = [F(kind="advisory", repo="acme/homebase", package="express", current="< 4.21.1", target="4.21.1",
            severity="critical", source_url="https://github.com/advisories/GHSA-1111-2222-3333", summary="Open redirect.",
            actionable=True, import_sites=[("a.js", 1, "x")]),
          F(kind="advisory", repo="acme/homebase", package="lodash", current=">= 4.0.0, < 4.17.21", target=None,
            severity="moderate", source_url="https://github.com/advisories/GHSA-4444-5555-6666", summary="Prototype pollution.")]
    text = note.render_advisory_section(date(2026, 9, 16), fs, JudgeReport(True, False, 0), {})
    assert text == (fixtures / "notes/advisory-append.md").read_text()


def test_tier1_unavailable_flag_and_raw_first_line():
    f = F(package="x", current="1.0.0", target="2.0.0", severity="major", raw="First line of notes\nmore")
    text = note.render_digest("2026-W37", GEN, 1, [f], JudgeReport(False, True, 0), 0, {})
    assert "summaries unavailable" in text
    assert "First line of notes" in text


def test_rerun_section_header():
    text = note.digest_rerun_section(GEN, 1, [], OK, 0, {})
    assert text.startswith("## Digest re-run 2026-09-14T07:00:00-04:00\n")


def test_upstream_sorts_major_before_minor():
    fs = [
        F(package="minor-pkg", current="1.0.0", target="1.1.0", severity="minor",
          source_url="https://example.com/minor"),
        F(package="major-pkg", current="1.0.0", target="2.0.0", severity="major",
          source_url="https://example.com/major"),
    ]
    text = note.render_digest("2026-W37", GEN, 1, fs, OK, 0, {})
    major_idx = text.index("major-pkg")
    minor_idx = text.index("minor-pkg")
    assert major_idx < minor_idx


def test_multiline_summary_and_breakage_stay_one_line():
    f = F(package="x", current="1.0.0", target="2.0.0", severity="major",
          summary="Line one.\nLine two.", breakage="Breaks a.js\nand b.js", actionable=True,
          import_sites=[("a.js", 1, "x")])
    text = note.render_digest("2026-W37", GEN, 1, [f], JudgeReport(True, False, 0), 0, {})
    matching = [l for l in text.splitlines() if "x 1.0.0 -> 2.0.0" in l]
    assert len(matching) == 1
    assert matching[0].endswith("[tier:: backlog]")


def test_advisory_section_reports_repo_errors():
    text = note.render_advisory_section(date(2026, 9, 16), [], OK, {"acme/recall": "git fetch failed"})
    assert "- fetch failed: recall: git fetch failed" in text
    assert "No new advisories." not in text


def test_fallback_summary_skips_release_note_headers():
    f = F(raw="### 12.3.0\n\nDropped Python 3.9.\nMore text.")
    text = note.line(f, JudgeReport(tier1_available=False, tier2_available=False, tier2_capped=0))
    assert "Dropped Python 3.9." in text and "###" not in text
