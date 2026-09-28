"""Hindsight adapter (retain/recall REST). Recall maps returned text back to known record ids."""
from .http_util import http_json


class HindsightClient:
    def __init__(self, url: str, bank: str, api_key: str = ""):
        self.base = f"{url.rstrip('/')}/v1/default/banks/{bank}"
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def retain(self, recs: list[dict]) -> None:
        items = [{
            "content": f'[{r["id"]}] ({r["type"]}, {r["service"]}, {r["date"]}) {r["title"]}. {r["text"]} '
                       f'Related: {", ".join(r["rel"]) or "none"}',
            "context": "engineering-history",
        } for r in recs]
        http_json("POST", f"{self.base}/memories", self.headers, {"items": items})

    def recall(self, query: str, known_ids: list[str]) -> list[str]:
        res = http_json("POST", f"{self.base}/memories/recall", self.headers, {"query": query}) or {}
        found: list[str] = []
        for x in res.get("results", []):
            text = " ".join(str(x.get(k, "")) for k in ("text", "content", "context"))
            found += [i for i in known_ids if i in text and i not in found]
        return found
