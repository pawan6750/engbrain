"""GitHub adapter: turns PRs, commits, issues and releases into linked memory records."""
import hashlib
import hmac
import re

from .http_util import http_json

URL_RE = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
REF_RE = re.compile(r"#(\d+)")


def _clip(t) -> str:
    return re.sub(r"\s+", " ", str(t or ""))[:400]


def verify_webhook_signature(secret: str, signature: str, body: bytes) -> bool:
    if not secret or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature[7:], expected)


class GitHubService:
    def __init__(self, token: str = ""):
        self.headers = {"Accept": "application/vnd.github+json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    @staticmethod
    def parse_url(url: str) -> tuple[str, str]:
        m = URL_RE.match(url.strip())
        if not m:
            raise ValueError("Use a URL like https://github.com/owner/repo")
        return m.group(1), m.group(2)

    def _get(self, path: str):
        return http_json("GET", f"https://api.github.com{path}", self.headers)

    def get_repository(self, o, n): return self._get(f"/repos/{o}/{n}")
    def get_pull_requests(self, o, n): return self._get(f"/repos/{o}/{n}/pulls?state=all&per_page=30")
    def get_commits(self, o, n): return self._get(f"/repos/{o}/{n}/commits?per_page=30")
    def get_issues(self, o, n): return self._get(f"/repos/{o}/{n}/issues?state=all&per_page=30")
    def get_releases(self, o, n): return self._get(f"/repos/{o}/{n}/releases?per_page=20")

    @staticmethod
    def webhook_records(event: str, payload: dict) -> list[dict]:
        repo = payload.get("repository") or {}
        service = repo.get("name") or repo.get("full_name") or "unknown"
        repo_url = repo.get("html_url", "")

        def record(rid, kind, date, title, text, url=""):
            return {"id": rid, "type": kind, "service": service, "date": str(date or "")[:10],
                    "title": _clip(title), "text": _clip(text) or _clip(title), "rel": [], "url": url}

        if event == "pull_request":
            item = payload.get("pull_request") or {}
            number = item.get("number")
            if number is None:
                return []
            action = payload.get("action", "updated")
            state = "merged" if item.get("merged") else item.get("state", "open")
            title = item.get("title", f"Pull request #{number}")
            return [record(f"PR-{number}", "pull_request", item.get("updated_at") or item.get("created_at"),
                           title, f"Pull request {action} ({state}). {item.get('body') or title}", item.get("html_url", ""))]

        if event == "issues":
            item = payload.get("issue") or {}
            number = item.get("number")
            if number is None or "pull_request" in item:
                return []
            action = payload.get("action", "updated")
            title = item.get("title", f"Issue #{number}")
            incident = any(re.search(r"incident|outage", label.get("name", ""), re.I)
                           for label in item.get("labels", [])) or bool(re.search(r"incident|outage", title, re.I))
            prefix, kind = ("INC", "incident") if incident else ("ISS", "issue")
            return [record(f"{prefix}-{number}", kind, item.get("updated_at") or item.get("created_at"),
                           title, f"Issue {action} ({item.get('state', 'open')}). {item.get('body') or title}",
                           item.get("html_url", ""))]

        if event == "push":
            records = []
            for commit in payload.get("commits", []):
                sha = commit.get("id", "")
                if not sha:
                    continue
                message = commit.get("message", "Commit")
                records.append(record(sha[:7], "commit", commit.get("timestamp"), message.splitlines()[0], message,
                                     f"{repo_url}/commit/{sha}" if repo_url else ""))
            return records

        if event == "release":
            item = payload.get("release") or {}
            tag = item.get("tag_name")
            if not tag:
                return []
            return [record(f"REL-{tag}", "deployment", item.get("published_at") or item.get("created_at"),
                           f"Release {tag}", item.get("body") or f"Release {tag}", item.get("html_url", ""))]

        if event == "deployment_status":
            deployment = payload.get("deployment") or {}
            status = payload.get("deployment_status") or {}
            if not deployment.get("id") or not status.get("id"):
                return []
            state = status.get("state", "updated")
            environment = deployment.get("environment", "unknown")
            return [record(f"DEP-{deployment['id']}-{status['id']}", "deployment", status.get("created_at"),
                           f"Deployment {environment}: {state}", status.get("description") or state,
                           status.get("target_url") or status.get("log_url", ""))]

        return []

    def ingest(self, url: str) -> list[dict]:
        o, n = self.parse_url(url)
        prs, commits = self.get_pull_requests(o, n), self.get_commits(o, n)
        issues, releases = self.get_issues(o, n), self.get_releases(o, n)
        linked = lambda t: [x for r in REF_RE.findall(t or "") for x in (f"PR-{r}", f"INC-{r}")]  # noqa: E731
        recs: list[dict] = []
        for p in prs:
            recs.append({"id": f"PR-{p['number']}", "type": "pull_request", "service": n,
                         "date": (p.get("merged_at") or p["created_at"])[:10], "title": p["title"],
                         "text": _clip(p.get("body")) or p["title"], "rel": linked(f"{p['title']} {p.get('body') or ''}"),
                         "url": p.get("html_url", "")})
        for c in commits:
            msg = c["commit"]["message"]
            recs.append({"id": c["sha"][:7], "type": "commit", "service": n, "date": c["commit"]["author"]["date"][:10],
                         "title": msg.split("\n")[0][:120], "text": _clip(msg), "rel": [f"PR-{r}" for r in REF_RE.findall(msg)],
                         "url": c.get("html_url", "")})
        for i in issues:
            if "pull_request" in i:
                continue
            inc = any(re.search(r"incident|outage", l["name"], re.I) for l in i.get("labels", [])) or bool(re.search(r"incident|outage", i["title"], re.I))
            recs.append({"id": f"{'INC' if inc else 'ISS'}-{i['number']}", "type": "incident" if inc else "issue", "service": n,
                         "date": i["created_at"][:10], "title": i["title"], "text": _clip(i.get("body")) or i["title"],
                         "rel": linked(f"{i['title']} {i.get('body') or ''}"), "url": i.get("html_url", "")})
        for r in releases:
            recs.append({"id": f"REL-{r['tag_name']}", "type": "deployment", "service": n,
                         "date": (r.get("published_at") or r["created_at"])[:10], "title": f"Release {r['tag_name']}",
                         "text": _clip(r.get("body")) or f"Release {r['tag_name']}", "rel": linked(r.get("body") or ""),
                         "url": r.get("html_url", "")})
        ids = {r["id"] for r in recs}
        for r in recs:
            r["rel"] = sorted({x for x in r["rel"] if x in ids and x != r["id"]})
        by_id = {r["id"]: r for r in recs}
        for r in recs:
            for t in r["rel"]:
                if r["id"] not in by_id[t]["rel"]:
                    by_id[t]["rel"].append(r["id"])
        return recs
