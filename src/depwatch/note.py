from datetime import date, datetime

from .judge import CAP_NOTE, JudgeReport
from .models import Finding


def week_id(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def note_path(folder: str, d: date) -> str:
    return f"{folder}/{week_id(d)}.md"


def _repo_name(repo: str) -> str:
    return repo.split("/")[-1]


def _repo_link(repo: str) -> str:
    return f"[{_repo_name(repo)}](https://github.com/{repo})"


def _summary(f: Finding, report: JudgeReport) -> str:
    if f.summary:
        return f" {f.summary}"
    if not report.tier1_available and f.raw:
        return f" {f.raw.splitlines()[0].strip()}"
    return ""


def _breakage(f: Finding, report: JudgeReport) -> str:
    if f.breakage and f.breakage != CAP_NOTE:
        return f" Breakage: {f.breakage}"
    if f.breakage == CAP_NOTE:
        return f" Breakage: {CAP_NOTE}."
    if f.qualifies_for_tier2 and not report.tier2_available:
        return " Breakage read unavailable."
    if f.kind == "release" and f.severity == "major" and not f.import_sites:
        return " No import sites found."
    return ""


def line(f: Finding, report: JudgeReport) -> str:
    box = "- [ ] " if f.actionable else "- "
    tail = " [tier:: backlog]" if f.actionable else ""
    if f.kind == "advisory":
        fix = f"fixed in {f.target}" if f.target else "no fix released"
        ghsa = f.source_url.rsplit("/", 1)[-1]
        body = (f"{_repo_link(f.repo)}: {f.package} {f.current}, [{ghsa}]({f.source_url}) ({f.severity}), {fix}."
                f"{_summary(f, report)}{_breakage(f, report)}")
    elif f.kind == "landed":
        day = (f.commit_date or "")[:10]
        short = (f.commit or "")[:7]
        if f.current and f.target:
            change = f"{f.package} {f.current} -> {f.target}"
        elif f.target:
            change = f"{f.package} added at {f.target}"
        else:
            change = f"{f.package} removed (was {f.current})"
        body = f"{day} `{short}`: [{change}]({f.source_url}) ({f.severity}).{_summary(f, report)}"
    else:
        body = (f"[{f.package} {f.current} -> {f.target}]({f.source_url}) ({f.severity})."
                f"{_summary(f, report)}{_breakage(f, report)}")
    return f"{box}{body}{tail}"


def render_frontmatter(week: str, generated: datetime, repos: int, findings: list[Finding], skipped: int) -> str:
    n = {k: sum(1 for f in findings if f.kind == k) for k in ("advisory", "landed", "release")}
    return ("---\n"
            "type: dependency-digest\n"
            f"week: {week}\n"
            f"generated: {generated.isoformat()}\n"
            f"repos: {repos}\n"
            "findings:\n"
            f"  advisories: {n['advisory']}\n"
            f"  landed: {n['landed']}\n"
            f"  releases: {n['release']}\n"
            f"skipped: {skipped}\n"
            "---\n")


def _body(findings: list[Finding], report: JudgeReport, repo_errors: dict[str, str]) -> str:
    if not findings and not repo_errors:
        return "No changes this week.\n"
    parts: list[str] = []
    if not report.tier1_available:
        parts.append("Note: summaries unavailable, the local model did not answer.\n")
    advisories = [f for f in findings if f.kind == "advisory"]
    if advisories:
        parts.append("## Advisories\n\n" + "\n".join(line(f, report) for f in advisories) + "\n")
    repos = sorted({f.repo for f in findings if f.kind != "advisory"} | set(repo_errors))
    for repo in repos:
        section = [f"## {_repo_name(repo)}\n"]
        if repo in repo_errors:
            section.append(f"- fetch failed: {repo_errors[repo]}\n")
        landed = [f for f in findings if f.repo == repo and f.kind == "landed"]
        if landed:
            section.append("### Landed\n" + "\n".join(line(f, report) for f in landed) + "\n")
        rel = [f for f in findings if f.repo == repo and f.kind == "release"]
        big = [f for f in rel if f.severity != "patch"]
        patches = [f for f in rel if f.severity == "patch"]
        if rel:
            lines = [line(f, report) for f in big]
            if patches:
                lines.append(f"- Patches: {', '.join(f.package for f in patches)} ({len(patches)}).")
            section.append("### Upstream\n" + "\n".join(lines) + "\n")
        parts.append("\n".join(section))
    return "\n".join(parts)


def render_digest(week: str, generated: datetime, repos: int, findings: list[Finding], report: JudgeReport,
                  skipped: int, repo_errors: dict[str, str]) -> str:
    return (render_frontmatter(week, generated, repos, findings, skipped)
            + f"\n# Dependencies {week}\n\n" + _body(findings, report, repo_errors))


def digest_rerun_section(generated: datetime, repos: int, findings: list[Finding], report: JudgeReport,
                         skipped: int, repo_errors: dict[str, str]) -> str:
    return f"## Digest re-run {generated.isoformat()}\n\n" + _body(findings, report, repo_errors)


def render_advisory_section(day: date, findings: list[Finding], report: JudgeReport) -> str:
    body = "\n".join(line(f, report) for f in findings) if findings else "No new advisories."
    return f"## Advisory {day.isoformat()}\n\n{body}\n"
