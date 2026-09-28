# EngBrain — Remember what your engineering team learned

Engineering-memory agent: traces *why* code exists, finds similar past incidents, warns about risky changes.
FastAPI backend (SQLite persistence, GitHub ingestion, Hindsight memory, pluggable LLM) serving a single-page UI.

## Run
```
cp .env.example .env            # add keys you want; all are optional
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload   # open http://localhost:8000
```
Or `docker compose up --build`. For Hindsight too: `docker compose --profile hindsight up` and set `HINDSIGHT_URL=http://hindsight:8888`.

## Live integrations
New demo, GitHub-ingested, and webhook records are stored locally and retained to Hindsight immediately when it is reachable. If Hindsight is unavailable, local memory remains available; Settings shows the most recent retain error, and **Sync all memories to Hindsight** retries the full store.

To receive GitHub events, set `GITHUB_WEBHOOK_SECRET` in `.env`, then configure a repository webhook with that same secret, content type `application/json`, and events for pull requests, issues, pushes, releases, and deployment statuses. Point it at `https://<public-host>/api/webhooks/github`; a local server needs a public tunnel for GitHub to reach it. The app validates GitHub's SHA-256 signature and streams accepted updates to open browser sessions over `/api/events`.

## Use
1. Settings → **Load demo history** (AcmePay) or **Ingest repository** (any `https://github.com/owner/repo`).
2. Ask EngBrain, Timeline, Incidents, Code Review. Click any source chip for details.
3. With `HINDSIGHT_URL` set, use **Sync** to retain records; questions then use hybrid recall.
4. With `LLM_API_KEY` set, answers gain an AI summary limited to retrieved evidence; unknown citations are flagged.

## API
`GET /api/health` · `POST /api/demo/load` · `POST /api/repository/connect {url}` · `POST /api/memory/sync` · `GET /api/records[/{id}]`
· `GET /api/incidents|decisions|deployments|timeline` · `POST /api/chat {question}` · `POST /api/code-review {diff,service}` · `POST /api/memory/search`

## Tests
`python -m unittest discover tests -v` (API tests run when fastapi is installed).

## Limitations
Retrieval is keyword + optional Hindsight recall (its response shape is matched by record id in text). Code-review risk detection is keyword-based.
GitHub ingest covers the latest 30 PRs/commits/issues and 20 releases (releases become deployments); decisions are not extracted automatically.
