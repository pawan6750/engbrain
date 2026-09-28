import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import ask, review
from .config import load_settings
from .demo import RECORDS
from .github_service import GitHubService, verify_webhook_signature
from .hindsight import HindsightClient
from .http_util import UpstreamError
from .llm import make_provider, unknown_citations
from .memory import MemoryService
from .store import SQLiteBackend

logging.basicConfig(level=logging.INFO)
cfg = load_settings()
Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
hs = HindsightClient(cfg.hindsight_url, cfg.hindsight_bank, cfg.hindsight_api_key) if cfg.hindsight_url else None
mem = MemoryService(SQLiteBackend(cfg.db_path), hs)
provider = make_provider(cfg)
github = GitHubService(cfg.github_token)

app = FastAPI(title="EngBrain")


class ChatIn(BaseModel): question: str = Field(min_length=3, max_length=1000)
class ReviewIn(BaseModel): diff: str = Field(min_length=1, max_length=20000); service: str = Field(min_length=1, max_length=100)
class SearchIn(BaseModel): query: str = Field(min_length=1, max_length=500); service: str | None = None
class ConnectIn(BaseModel): url: str = Field(min_length=10, max_length=300)


@app.exception_handler(UpstreamError)
async def _upstream(_, e): return JSONResponse({"detail": str(e)}, status_code=502)
@app.exception_handler(ValueError)
async def _value(_, e): return JSONResponse({"detail": str(e)}, status_code=400)


@app.get("/api/health")
def health():
    return {"status": "ok", "memories": len(mem.b.all()),
            "integrations": {"hindsight": hs is not None, "github": True, "llm": provider.__class__.__name__ != "MockProvider",
                             "github_token": bool(cfg.github_token), "github_webhook": bool(cfg.github_webhook_secret)},
            "hindsight_error": mem.hindsight_error}

@app.post("/api/demo/load")
def load_demo():
    mem.remember_many(RECORDS)
    return {"loaded": len(RECORDS)}

@app.post("/api/repository/connect")
def connect(b: ConnectIn):
    recs = github.ingest(b.url)
    mem.remember_many(recs)
    return {"ingested": len(recs)}


@app.post("/api/webhooks/github")
async def github_webhook(request: Request):
    if not cfg.github_webhook_secret:
        raise HTTPException(503, "Set GITHUB_WEBHOOK_SECRET to enable GitHub webhooks")
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    if not verify_webhook_signature(cfg.github_webhook_secret, signature, body):
        raise HTTPException(401, "Invalid GitHub webhook signature")
    event = request.headers.get("x-github-event", "")
    payload = await request.json()
    recs = github.webhook_records(event, payload)
    mem.remember_many(recs)
    return {"received": True, "event": event, "ingested": len(recs)}


@app.get("/api/events")
async def events():
    async def stream():
        last_version = mem.version
        yield ": connected\n\n"
        while True:
            await asyncio.sleep(0.5)
            version = mem.version
            if version != last_version:
                last_version = version
                yield f"event: memory\ndata: {json.dumps({'version': version})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/memory/sync")
def sync(): return {"synced": mem.sync()}

@app.get("/api/records")
def records(): return mem.get_timeline()

@app.get("/api/records/{rid}")
def record(rid: str):
    r = mem.get(rid)
    if not r: raise HTTPException(404, "Record not found")
    return {**r, "related": mem.search_related(rid, 1)}

def _by_type(t: str): return [r for r in mem.get_timeline() if r["type"] == t]
@app.get("/api/incidents")
def incidents(): return _by_type("incident")
@app.get("/api/decisions")
def decisions(): return _by_type("decision")
@app.get("/api/deployments")
def deployments(): return _by_type("deployment")
@app.get("/api/timeline")
def timeline(service: str | None = None): return mem.get_timeline(service)

@app.post("/api/chat")
def chat(b: ChatIn):
    res = ask(b.question, mem)
    notes = [mem.last_note] if mem.last_note else []
    summary, unknown = None, []
    if res["evidence"]:
        try:
            summary = provider.summarize(b.question, res["evidence"])
            unknown = unknown_citations(summary, res["evidence"]) if summary else []
        except UpstreamError as e:
            notes.append(f"AI summary unavailable: {e}")
    return {**res, "summary": summary, "unknown_ids": unknown, "notes": notes}

@app.post("/api/code-review")
def code_review(b: ReviewIn): return review(b.diff, b.service, mem)

@app.post("/api/memory/search")
def search(b: SearchIn): return mem.recall(b.query, b.service)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
