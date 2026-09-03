# career-station: plan

Self-hosted job-search station. Finds roles, scores them against Steve's profile, notifies on strong matches, drafts tailored CVs and cover notes, tracks each role through the pipeline, and researches companies ahead of interviews.

Design principle: the app does the searching and the grind; Steve does the deciding. Rejections are logged, never surfaced individually.

Sibling of cupid-station and Arkadia Forge. Same stack, same dev loop, same deployment pattern.

## Status

- Phase 0: done, deployed on Coolify (HV02), Reed returning results. 3 Sep 2026.
- Phase 1a: filters, profile page, scoring queue and score endpoint, Discord notify on score. Deployed 3 Sep 2026; bot scoring on cron, first batch 33 roles.
- Phase 1b: Adzuna, RSS and LinkedIn sources, cross-source merge, agency tag and direct-only toggle. Built 3 Sep 2026.
- Decision: no LLM in the app. Scoring and documents are done by the Claude Code bot on ark-agent-01 (Max subscription) via the API. See `bot/score-roles.md`.

## Goals (v0.1)

1. Aggregate roles from multiple sources every few hours, deduplicated.
2. Score each role for fit against a master profile and a set of hard filters.
3. Push a Discord notification for any role scoring above threshold.
4. Web UI: list of roles with score, salary, location, source, and a one-tap "not interested".
5. Never show a rejection count, rate, or streak anywhere in the UI.

## Non-goals (for now)

- Auto-submitting applications.
- Logging in to job boards with Steve's credentials.
- Replacing the existing Gmail inbox sweep. career-station consumes its labels; it does not re-implement them.

## Stack

- Backend: FastAPI, Python 3.12, SQLite (WAL), APScheduler for the crawl loop
- Frontend: Vite + React + TypeScript + Tailwind v4 (design tokens in `frontend/src/index.css` via `@theme static`)
- Built frontend lands in `backend/static/`, served by FastAPI
- Data: `/data` named volume in Coolify (`career-data`), single backup target
- Notifications: Discord webhook (env `CAREER_DISCORD_WEBHOOK`)

## Deployment

- Repo: `career-station` on GitHub, canonical copy on Steve's PC in the connected folder alongside cupid-station
- Coolify on HV02 builds from GitHub. Unpushed commits never deploy.
- Internal DNS via Pi-hole: `career.arkadia.network` pointed at HV02's edge
- Single container. No external ports beyond the reverse proxy.

## Data model

```
sources        id, name, kind (api|rss|scrape), enabled, last_run, last_ok
roles          id, source_id, external_id, url, title, company, location,
               remote_flag, salary_min, salary_max, salary_text, description,
               posted_at, first_seen, last_seen, hash
scores         role_id, score (0-100), reasons (json), scored_at, model
status         role_id, state (new|shortlisted|applied|progressing|rejected|declined|dismissed),
               changed_at, note
notifications  role_id, channel, sent_at
profile        singleton: markdown master profile, hard filters (json)
research       role_id, company_brief (markdown), generated_at
documents      role_id, kind (cv|cover), content (markdown), generated_at
```

Dedupe key: normalised (title, company, location) plus URL host. Same role from two boards collapses to one record with multiple source links.

## Sources (v0.1)

Ordered by reliability. Do not build on fragile scrapers first.

1. Reed API (free key, JSON, salary included) 
2. Adzuna API (free key, aggregates many boards, salary estimates)
3. CWJobs and Technojobs via RSS where available
4. LinkedIn and Indeed: guest search pages, HTML scrape, treated as best-effort. Expect breakage. Failures must not stop the run; log and continue.
5. Otta: no public API, defer to v0.2 or skip

Cross-source merge: dedupe key is normalised title, company and the first token of location. A second sighting fills in description and salary the first lacked. Agency detection is a name heuristic in the UI (recruit, resourcing, placements, etc.) with a direct-only toggle.

Each source is a class with `fetch() -> list[RawRole]`. A broken source returns empty and sets `last_ok = false`. The UI shows source health so silent failure is visible.

## Search terms and filters

Search terms (env or profile table, editable in UI):

```
"Modern Workplace", "TechOps", "IT Operations Manager", "IT Service Manager",
"Infrastructure Engineer", "Platform Engineer", "IAM Engineer", "Identity Engineer",
"EUC Lead", "Endpoint Engineer", "IT Manager", "Head of IT"
```

Hard filters (roles failing these are stored but never scored or notified):

- Location: remote, hybrid within reach of Polegate (Brighton, Eastbourne, Lewes, Crawley, Gatwick corridor, London hybrid 2 days or fewer), or explicitly UK-wide remote
- Salary: if stated, max must be at or above the floor in the profile (currently £74k). Unstated salary passes the filter but is flagged.
- Exclude: roles requiring active SC/DV clearance unless the ad says sponsorship offered; pure service desk analyst roles; contract-only under 6 months

## Fit scoring

Done by the bot, not the app. The app exposes `GET /api/queue/unscored` and `PUT /api/roles/{id}/score`. Task spec in `bot/score-roles.md`. Output shape:

```json
{"score": 0-100, "reasons": ["..."], "gaps": ["..."], "salary_band_guess": "..."}
```

Prompt includes the master profile, the hard-filter results, and the job description. Score is a fit judgement, not a "will I get it" judgement. Roles at 75 and above trigger a notification. Threshold editable in UI.

The bot runs 20 minutes after each crawl. Queue returns 40 at a time.

## Notifications

Discord webhook message per role above threshold: title, company, location, salary, score, top two reasons, link to the role in career-station. One message per role, rate-limited to 10 per run. No notifications for rejections, ever.

Weekly digest (Monday 10:00 Europe/London, aligned with the morning brief): roles found, shortlisted, applied, progressing. Rejections appear as a single line count only in this digest and nowhere else.

## Web UI (v0.1)

Single page, mobile-first (Steve will mostly use this on his phone):

- Role list sorted by score, then recency. Card shows title, company, location, salary, score, source badges.
- Filter chips: new, shortlisted, applied, progressing, remote only, above floor
- Card actions: shortlist, dismiss, open ad, mark applied
- Source health strip at the bottom
- Profile page: edit master profile markdown, search terms, filters, threshold

## Master profile

One document, three parts: a shared core (who, scale, stacks, constraints), an Engineer track section, and a Management track section. The bot decides a role's track from the ad and scores against that section; `scores.track` is stored and shown as a tag. Phase 3 picks the CV to draft from by track.

A markdown file the bot reads for scoring and (Phase 3) for CV generation. Seed from the existing CVs and the job-search notes. Sections: summary, roles and outcomes, stacks (identity, endpoint, cloud, automation), scale numbers, what I want, what I will not do, salary floor, location constraints.

Stored in the DB but exportable and importable as a file so it can be edited outside the app.

## Phase plan

### Phase 0: skeleton and smoke test
- Repo scaffold matching cupid-station layout
- Reed source only, fetch and store
- Bare list UI
- Deploy to Coolify, confirm data volume persists across redeploy

### Phase 1: v0.1 as above
- Adzuna, RSS sources, LinkedIn and Indeed best-effort
- Dedupe, filters, scoring, Discord notifications
- Full role list UI with actions and source health
- Playwright screenshots of list and profile pages

### Phase 2: pipeline sync
- Read the Gmail Job Search labels (Applied, Progressing, Rejected, Declined) and update role status. Match on company and title, fuzzy. Two options: (a) the existing inbox sweep writes a JSON status file the app polls, (b) the app talks to Gmail directly via OAuth. Prefer (a): keeps Gmail credentials out of the app.
- Weekly digest

### Phase 3: documents
- "Draft CV" and "Draft cover note" per role: master profile plus job description in, markdown out, editable in UI, export to PDF and DOCX
- Bot hand-off: an endpoint `POST /roles/{id}/handoff` that writes a task file the Claude Code bot can pick up for a fuller tailored CV session

### Phase 4: research
- Per role: company brief from web search (size, sector, recent news, Glassdoor sentiment, Companies House filing summary, likely tech stack from job ads and engineering blogs). Cached, regenerated on demand.
- Interview prep view: brief plus the role's reasons and gaps

## Dev loop

Identical to cupid-dev-loop:

1. Edit in `/home/claude/career-station`
2. `cd frontend && npm run build`
3. Start uvicorn detached with `setsid ... < /dev/null &`, seed with curl, hit the API
4. Playwright screenshots of every changed page, read them before shipping
5. `tar czf` explicit changed paths only. Never `node_modules`, `backend/static`, `data/`, `__pycache__`, `.git`
6. Deliver tar plus screenshots
7. Extract on device, `git add -A`, review staged, commit with body and trailer
8. Steve pushes from Windows and redeploys in Coolify

## Gotchas carried over from cupid-station

- Tailwind v4 tree-shakes `@theme static` tokens unless referenced somewhere other than inline style
- SQLite migrations are additive `PRAGMA table_info` checks in `db.py::_migrate`; new columns go in both `schema.sql` and `_migrate`
- Plain `&` in compound commands gets reaped; use `setsid`
- Never `pkill -f` a pattern that appears in the same compound command

## Open questions

- Reed and Adzuna API keys: Steve to register (both free, a few minutes each)
- Discord channel for notifications: reuse the existing alerting channel or create `#career`?
- Does the existing inbox sweep already write anywhere the app could read, or does Phase 2 need a small addition to it?
- Master profile seed: which CV is the best starting point (Anthropic build, Sopra build, or the general one)?
