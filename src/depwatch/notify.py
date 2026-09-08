import httpx


class Notifier:
    def __init__(self, client: httpx.Client, topic: str | None):
        self.client, self.topic = client, topic

    def failure(self, text: str) -> None:
        if not self.topic:
            return
        try:
            self.client.post(f"https://ntfy.sh/{self.topic}", content=text[:200].encode(),
                             headers={"Title": "depwatch failure"}, timeout=10)
        except httpx.HTTPError:
            pass
