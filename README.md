# career-station

Finds roles, scores them against a profile, notifies on strong matches. Phase 0: Reed source, list UI, status actions.

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

Plan and phases: see `career-station-plan.md`.
