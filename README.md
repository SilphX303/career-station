# career-station

Finds roles, scores them against a profile, notifies on strong matches. Sources: Reed and Adzuna (APIs), RSS feeds, LinkedIn guest search (best effort). Scoring by the Claude Code bot.

## Run locally

    cd frontend && npm install && npm run build && cd ..
    pip install -r backend/requirements.txt
    cd backend && CAREER_DATA_DIR=../data CAREER_REED_KEY=yourkey uvicorn app.main:app --reload

Without a key, use the mock: `python dev/mock_reed.py` then set `CAREER_REED_KEY=x CAREER_REED_BASE=http://127.0.0.1:8765`.

## Deploy (Coolify)

Dockerfile build from GitHub. Add a named volume `career-data` mounted at `/data`. Set env from `.env.example`.

## API

- `GET /api/roles?state=` list (default hides dismissed/rejected/declined)
- `PUT /api/roles/{id}/status` `{"state": "shortlisted"}`
- `POST /api/crawl` run all sources now
- `GET /api/sources` health
- `GET|PUT /api/profile`
- `GET /api/queue/unscored` for the scoring bot
- `PUT /api/roles/{id}/score` `{"score": 88, "reasons": [], "gaps": []}`; notifies Discord at or above threshold

- `POST /api/sync/status` `{"source":"inbox","items":[{"company":"..","title":"..","state":"applied","note":".."}]}` fuzzy-matches inbox findings to roles

- `POST /api/roles/{id}/documents` `{"kind":"cv"|"cover"}` queue a draft; `GET /api/queue/documents` for the bot; `PUT /api/documents/{id}` result

Scoring and drafting are done by the Claude Code bot, see `bot/score-roles.md` and `bot/draft-documents.md`.

Plan and phases: see `career-station-plan.md`.
