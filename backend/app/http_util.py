"""Tiny stdlib JSON-over-HTTP helper so adapters share error handling."""
import json
import urllib.error
import urllib.request


class UpstreamError(Exception):
    """An external service (GitHub, Hindsight, LLM) failed."""


def http_json(method: str, url: str, headers: dict | None = None, body: dict | None = None, timeout: int = 25):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", "User-Agent": "EngBrain/1.0", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise UpstreamError(f"HTTP {e.code} from {urllib.request.urlparse(url).netloc}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise UpstreamError(f"Request failed: {getattr(e, 'reason', e)}") from e
