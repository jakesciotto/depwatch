import httpx

from depwatch.notify import Notifier


def test_failure_posts_truncated():
    seen = []
    def handler(req):
        seen.append((str(req.url), req.headers.get("title"), req.content.decode()))
        return httpx.Response(200)
    Notifier(httpx.Client(transport=httpx.MockTransport(handler)), "topic").failure("x" * 500)
    assert seen == [("https://ntfy.sh/topic", "depwatch failure", "x" * 200)]


def test_failure_never_raises_and_noop_without_topic():
    def handler(req): raise httpx.ConnectError("down")
    Notifier(httpx.Client(transport=httpx.MockTransport(handler)), "topic").failure("a")
    Notifier(httpx.Client(transport=httpx.MockTransport(handler)), None).failure("a")
