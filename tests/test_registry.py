import httpx

from depwatch.registry import Registry, RegistryInfo

NPM = {"dist-tags": {"latest": "4.7.0"}, "repository": {"url": "git+https://github.com/honojs/hono.git"}}
PYPI = {"info": {"version": "3.2.1", "project_urls": {"Homepage": "https://www.psycopg.org/",
                                                       "Source": "https://github.com/psycopg/psycopg"}}}


def make(handler):
    return Registry(httpx.Client(transport=httpx.MockTransport(handler)))


def test_npm_latest_and_repo():
    calls = []
    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, json=NPM)
    r = make(handler)
    assert r.latest("hono", "npm") == RegistryInfo("4.7.0", "honojs/hono")
    assert r.latest("hono", "npm") == RegistryInfo("4.7.0", "honojs/hono")
    assert calls == ["https://registry.npmjs.org/hono"]


def test_scoped_npm_name_is_url_encoded():
    # httpx.URL.path always fully unquotes, so assert on the raw wire path
    # to verify the slash is actually percent-encoded in the outgoing request.
    seen = []
    def handler(req):
        seen.append(req.url.raw_path.decode())
        return httpx.Response(200, json={"dist-tags": {"latest": "1.0.0"}})
    make(handler).latest("@types/node", "npm")
    assert seen == ["/@types%2Fnode"]


def test_pypi_latest_and_repo():
    r = make(lambda req: httpx.Response(200, json=PYPI))
    assert r.latest("psycopg", "pypi") == RegistryInfo("3.2.1", "psycopg/psycopg")


def test_404_returns_none_and_counts():
    r = make(lambda req: httpx.Response(404))
    assert r.latest("nope", "npm") is None
    assert r.skipped == 1


def test_network_error_returns_none():
    def handler(req):
        raise httpx.ConnectError("down")
    r = make(handler)
    assert r.latest("x", "pypi") is None
    assert r.skipped == 1


def test_docker_is_not_looked_up():
    r = make(lambda req: (_ for _ in ()).throw(AssertionError("no call")))
    assert r.latest("node", "docker") is None
    assert r.skipped == 0
