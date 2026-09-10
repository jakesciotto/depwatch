import json

import httpx

from depwatch.models import Dependency
from depwatch.osv import OSV


def dep(name, eco, version, path="package.json"):
    return Dependency(name, eco, version, "prod", path)


def vuln(vid, severity="HIGH", aliases=(), package=("hono", "npm"), fixed="4.6.5"):
    name, eco = package
    rec = {"id": vid, "aliases": list(aliases), "published": "2024-10-15T17:43:50Z",
           "summary": "Summary", "details": "Details",
           "affected": [{"package": {"name": name, "ecosystem": eco},
                         "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": fixed}]}]}]}
    if severity:
        rec["database_specific"] = {"severity": severity}
    return rec


class Api:
    """Fake api.osv.dev. Batch answers keyed by (ecosystem, name, version), details keyed by id."""

    def __init__(self, batch, details):
        self.batch, self.details, self.requests = batch, details, []

    def __call__(self, req):
        self.requests.append(req)
        if req.url.path == "/v1/querybatch":
            queries = json.loads(req.content)["queries"]
            results = [{"vulns": [{"id": i, "modified": "2024-10-15T17:43:50Z"} for i in
                                  self.batch.get((q["package"]["ecosystem"], q["package"]["name"], q["version"]), [])]}
                       for q in queries]
            return httpx.Response(200, json={"results": results})
        vid = req.url.path.rsplit("/", 1)[-1]
        if vid in self.details:
            return httpx.Response(200, json=self.details[vid])
        return httpx.Response(404)


def make(api):
    return OSV(httpx.Client(transport=httpx.MockTransport(api)))


def test_alerts_batch_queries_and_fetches_each_vuln_once():
    api = Api(batch={("npm", "hono", "4.6.1"): ["GHSA-1"], ("PyPI", "pillow", "9.0.0"): ["GHSA-2"],
                     ("npm", "hono", "4.6.0"): ["GHSA-1"]},
              details={"GHSA-1": vuln("GHSA-1"),
                       "GHSA-2": vuln("GHSA-2", severity="MODERATE", package=("pillow", "PyPI"), fixed="9.0.1")})
    alerts = make(api).alerts([dep("hono", "npm", "4.6.1"), dep("pillow", "pypi", "9.0.0", path="pyproject.toml"),
                               dep("hono", "npm", "4.6.0", path="web/package.json")])
    assert [r.url.path for r in api.requests] == ["/v1/querybatch", "/v1/vulns/GHSA-1", "/v1/vulns/GHSA-2"]
    a = alerts[0]
    assert (a.ghsa_id, a.severity, a.package, a.ecosystem, a.vulnerable_range, a.first_patched) == (
        "GHSA-1", "high", "hono", "npm", "4.6.1", "4.6.5")
    assert (a.summary, a.description, a.permalink, a.manifest_path, a.created_at) == (
        "Summary", "Details", "https://github.com/advisories/GHSA-1", "package.json", "2024-10-15T17:43:50Z")
    assert [(x.ghsa_id, x.package, x.vulnerable_range, x.manifest_path) for x in alerts] == [
        ("GHSA-1", "hono", "4.6.1", "package.json"), ("GHSA-2", "pillow", "9.0.0", "pyproject.toml"),
        ("GHSA-1", "hono", "4.6.0", "web/package.json")]


def test_docker_dependencies_are_not_queried():
    api = Api(batch={("npm", "hono", "4.6.1"): []}, details={})
    make(api).alerts([Dependency("node", "docker", "22", "base-image", "Dockerfile"), dep("hono", "npm", "4.6.1")])
    queries = json.loads(api.requests[0].content)["queries"]
    assert [q["package"]["name"] for q in queries] == ["hono"]


def test_ghsa_alias_becomes_the_id_and_permalink():
    api = Api(batch={("PyPI", "pillow", "9.0.0"): ["PYSEC-1"]},
              details={"PYSEC-1": vuln("PYSEC-1", aliases=["CVE-2022-1", "GHSA-9"], package=("pillow", "PyPI"))})
    a, = make(api).alerts([dep("pillow", "pypi", "9.0.0")])
    assert (a.ghsa_id, a.permalink) == ("GHSA-9", "https://github.com/advisories/GHSA-9")


def test_record_without_ghsa_links_to_osv():
    api = Api(batch={("PyPI", "pillow", "9.0.0"): ["PYSEC-2"]},
              details={"PYSEC-2": vuln("PYSEC-2", aliases=["CVE-2022-2"], package=("pillow", "PyPI"))})
    a, = make(api).alerts([dep("pillow", "pypi", "9.0.0")])
    assert (a.ghsa_id, a.permalink) == ("PYSEC-2", "https://osv.dev/vulnerability/PYSEC-2")


def test_alias_record_is_dropped_when_its_ghsa_is_also_listed():
    api = Api(batch={("PyPI", "pillow", "9.0.0"): ["GHSA-9", "PYSEC-1"]},
              details={"GHSA-9": vuln("GHSA-9", severity="CRITICAL", package=("pillow", "PyPI")),
                       "PYSEC-1": vuln("PYSEC-1", severity=None, aliases=["GHSA-9"], package=("pillow", "PyPI"))})
    alerts = make(api).alerts([dep("pillow", "pypi", "9.0.0")])
    assert [(a.ghsa_id, a.severity) for a in alerts] == [("GHSA-9", "critical")]


def test_first_patched_is_smallest_fixed_newer_than_installed():
    rec = vuln("GHSA-3")
    rec["affected"] = [
        {"package": {"name": "other", "ecosystem": "npm"},
         "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "9.9.9"}]}]},
        {"package": {"name": "hono", "ecosystem": "npm"},
         "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "1.2.3"},
                                                   {"introduced": "2.0.0"}, {"fixed": "2.1.0"},
                                                   {"introduced": "3.0.0"}, {"fixed": "3.0.1"}]}]},
    ]
    api = Api(batch={("npm", "hono", "2.0.5"): ["GHSA-3"]}, details={"GHSA-3": rec})
    a, = make(api).alerts([dep("hono", "npm", "2.0.5")])
    assert a.first_patched == "2.1.0"


def test_missing_severity_label_falls_back_to_moderate():
    api = Api(batch={("npm", "hono", "4.6.1"): ["GHSA-4"]}, details={"GHSA-4": vuln("GHSA-4", severity=None)})
    a, = make(api).alerts([dep("hono", "npm", "4.6.1")])
    assert a.severity == "moderate"


def test_batch_is_chunked_at_1000_queries():
    deps = [dep(f"p{i}", "npm", "1.0.0") for i in range(1001)]
    api = Api(batch={}, details={})
    make(api).alerts(deps)
    sizes = [len(json.loads(r.content)["queries"]) for r in api.requests]
    assert sizes == [1000, 1]
