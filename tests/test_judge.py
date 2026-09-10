import json
from pathlib import Path

import httpx

from depwatch import judge
from depwatch.models import Finding


def finding(kind="release", sev="major", repo="o/r", pkg="hono"):
    return Finding(kind=kind, repo=repo, package=pkg, ecosystem="npm", current="4.6.1", target="5.0.0",
                   severity=sev, source_url="u", raw="Breaking: removed foo()")


def tier1(handler):
    return judge.Tier1(httpx.Client(transport=httpx.MockTransport(handler)), "http://llm/v1", "chat")


def test_tier1_sets_summary_and_risk():
    seen = []
    def handler(req):
        seen.append((str(req.url), json.loads(req.content)))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"summary": "Removed foo.", "risk": "high"}'}}]})
    t = tier1(handler)
    f = finding()
    t.annotate(f)
    assert (f.summary, f.risk) == ("Removed foo.", "high")
    url, body = seen[0]
    assert url == "http://llm/v1/chat/completions"
    assert body["model"] == "chat" and body["temperature"] == 0 and body["response_format"] == {"type": "json_object"}
    assert "hono" in body["messages"][1]["content"] and "Breaking: removed foo()" in body["messages"][1]["content"]


def test_tier1_bad_json_leaves_none():
    t = tier1(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}))
    f = finding(); t.annotate(f)
    assert f.summary is None and f.risk is None and t.available


def test_tier1_connection_error_marks_unavailable():
    calls = []
    def handler(req):
        calls.append(1); raise httpx.ConnectError("down")
    t = tier1(handler)
    t.annotate(finding()); t.annotate(finding())
    assert not t.available and len(calls) == 1


class FakeParsed:
    def __init__(self, breakage, actionable):
        self.parsed_output = judge.Breakage(breakage=breakage, actionable=actionable)


class FakeMessages:
    def __init__(self, outcome): self.outcome, self.calls = outcome, []
    def parse(self, **kw):
        self.calls.append(kw)
        if isinstance(self.outcome, Exception): raise self.outcome
        return self.outcome


class FakeAnthropic:
    def __init__(self, outcome): self.messages = FakeMessages(outcome)


def test_tier2_sets_breakage():
    client = FakeAnthropic(FakeParsed("server/src/app.ts:12 calls foo().", True))
    t = judge.Tier2(client, "claude-sonnet-5", max_calls=10)
    f = finding(); f.import_sites = [("server/src/app.ts", 12, "import { foo } from 'hono'")]
    t.read(f)
    assert (f.breakage, f.actionable, t.calls) == ("server/src/app.ts:12 calls foo().", True, 1)
    kw = client.messages.calls[0]
    assert kw["model"] == "claude-sonnet-5" and kw["output_format"] is judge.Breakage
    assert "server/src/app.ts:12: import { foo } from 'hono'" in kw["messages"][0]["content"]


def test_tier2_connection_error_marks_unavailable():
    import anthropic
    client = FakeAnthropic(anthropic.APIConnectionError(request=httpx.Request("POST", "http://x")))
    t = judge.Tier2(client, "claude-sonnet-5", max_calls=10)
    f = finding(); t.read(f)
    assert not t.available and f.breakage is None


def test_run_applies_cap_and_actionable_rule(tmp_path: Path):
    (tmp_path / "a.ts").write_text("import 'hono'\n")
    ok = tier1(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"summary": "s", "risk": "low"}'}}]}))
    t2 = judge.Tier2(FakeAnthropic(FakeParsed("b", False)), "claude-sonnet-5", max_calls=1)
    fs = [finding(pkg="hono"), finding(pkg="hono"), finding(sev="patch", pkg="hono"),
          finding(kind="advisory", sev="critical", pkg="none"), finding(kind="landed", pkg="hono")]
    report = judge.run(fs, lambda repo: tmp_path, ok, t2)
    assert [f.import_sites != [] for f in fs] == [True, True, True, False, False]
    assert [f.breakage for f in fs] == ["b", "not analysed: run cap reached", None, None, None]
    assert [f.actionable for f in fs] == [False, True, False, False, False]
    assert [f.summary for f in fs] == ["s", "s", None, "s", "s"]
    assert (report.tier1_available, report.tier2_available, report.tier2_capped) == (True, True, 1)


def test_run_with_tier2_unavailable_marks_qualifying_actionable(tmp_path: Path):
    import anthropic
    (tmp_path / "a.ts").write_text("import 'hono'\n")
    ok = tier1(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"summary": "s", "risk": "low"}'}}]}))
    t2 = judge.Tier2(FakeAnthropic(anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))), "m", 10)
    fs = [finding(), finding(sev="minor")]
    report = judge.run(fs, lambda repo: tmp_path, ok, t2)
    assert [f.actionable for f in fs] == [True, False]
    assert not report.tier2_available


def test_imported_advisory_stays_actionable_despite_tier2_false(tmp_path: Path):
    (tmp_path / "a.ts").write_text("import 'hono'\n")
    ok = tier1(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"summary": "s", "risk": "low"}'}}]}))
    t2 = judge.Tier2(FakeAnthropic(FakeParsed("no code change needed", False)), "m", 10)
    f = finding(kind="advisory", sev="critical", pkg="hono")
    judge.run([f], lambda repo: tmp_path, ok, t2)
    assert f.breakage == "no code change needed"
    assert f.actionable is True


def test_advisory_actionable_requires_import_sites(tmp_path: Path):
    import anthropic
    ok = tier1(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"summary": "s", "risk": "low"}'}}]}))

    imported = tmp_path / "imported"
    imported.mkdir()
    (imported / "a.ts").write_text("import 'hono'\n")
    t2 = judge.Tier2(FakeAnthropic(anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))), "m", 10)
    f_imported = finding(kind="advisory", sev="critical", pkg="hono")
    judge.run([f_imported], lambda repo: imported, ok, t2)
    assert f_imported.actionable is True

    empty = tmp_path / "empty"
    empty.mkdir()
    t2 = judge.Tier2(FakeAnthropic(anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))), "m", 10)
    f_not_imported = finding(kind="advisory", sev="critical", pkg="hono")
    judge.run([f_not_imported], lambda repo: empty, ok, t2)
    assert f_not_imported.actionable is False


def test_tier2_type_error_marks_unavailable():
    t = judge.Tier2(FakeAnthropic(TypeError("no auth")), "claude-sonnet-5", max_calls=10)
    f = finding(); t.read(f)
    assert not t.available and f.breakage is None


def test_tier2_other_error_keeps_available():
    t = judge.Tier2(FakeAnthropic(ValueError("bad shape")), "claude-sonnet-5", max_calls=10)
    f = finding(); t.read(f)
    assert t.available and f.breakage is None


def local_tier2(handler, max_calls=10):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return judge.LocalTier2(client, "http://llm/v1", "deep", max_calls)


def test_local_tier2_sets_breakage():
    seen = []
    def handler(req):
        seen.append((str(req.url), json.loads(req.content)))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"breakage": "a.ts:1 calls foo().", "actionable": true}'}}]})
    t = local_tier2(handler)
    f = finding(); f.import_sites = [("a.ts", 1, "import { foo } from 'hono'")]
    t.read(f)
    assert (f.breakage, f.actionable, t.calls) == ("a.ts:1 calls foo().", True, 1)
    url, body = seen[0]
    assert url == "http://llm/v1/chat/completions"
    assert body["model"] == "deep"
    assert body["max_tokens"] == 12000
    assert body["response_format"] == {"type": "json_object"}
    assert "a.ts:1: import { foo } from 'hono'" in body["messages"][1]["content"]


def test_local_tier2_bad_json_leaves_breakage_none():
    t = local_tier2(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}))
    f = finding(); t.read(f)
    assert f.breakage is None and t.available


def test_local_tier2_truncated_leaves_breakage_none():
    t = local_tier2(lambda req: httpx.Response(200, json={"choices": [{
        "finish_reason": "length", "message": {"content": ""}}]}))
    f = finding(); t.read(f)
    assert f.breakage is None and t.available


def test_local_tier2_connection_error_marks_unavailable():
    calls = []
    def handler(req):
        calls.append(1); raise httpx.ConnectError("down")
    t = local_tier2(handler)
    t.read(finding()); t.read(finding())
    assert not t.available and len(calls) == 1


def test_run_applies_cap_with_local_tier2(tmp_path: Path):
    (tmp_path / "a.ts").write_text("import 'hono'\n")
    ok = tier1(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"summary": "s", "risk": "low"}'}}]}))
    calls = []
    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"breakage": "b", "actionable": false}'}}]})
    t2 = local_tier2(handler, max_calls=1)
    fs = [finding(pkg="hono"), finding(pkg="hono")]
    report = judge.run(fs, lambda repo: tmp_path, ok, t2)
    assert [f.breakage for f in fs] == ["b", "not analysed: run cap reached"]
    assert len(calls) == 1
    assert report.tier2_capped == 1


def test_tiers_without_base_url_are_off():
    t1 = judge.Tier1(httpx.Client(), "", "")
    f = finding()
    t1.annotate(f)
    assert not t1.available and f.summary is None
    assert not judge.LocalTier2(httpx.Client(), "", "", 10).available
