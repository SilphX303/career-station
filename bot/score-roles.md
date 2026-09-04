# Task: score unscored roles

Runs on ark-agent-01 (Claude Code, Max subscription). Schedule: every 4 hours, offset 20 minutes after the crawl, plus on demand.

Env: `CAREER_URL` (https://career.arkadia.network, https not http; http redirects and curl without -L returns nothing)

## Steps

1. The wrapper fetches `GET $CAREER_URL/api/queue/unscored?limit=40` and passes the JSON to the agent on stdin (or inline in the prompt).
   Response: `{ "profile": "<markdown>", "threshold": 75, "roles": [ {id, title, company, location, remote_flag, salary_min, salary_max, salary_text, url, description, posted_at}, ... ] }`
   If `roles` is empty, stop.
   If `profile` is empty, stop and post to Discord: "career-station: profile is empty, nothing to score against."

2. For each role, first decide which track it belongs to by reading the ad, not the title:
   - `engineer`: hands-on delivery is the core of the job (building, migrating, automating, administering)
   - `management`: leading people or owning a function is the core (team lead, service manager, head of)
   Then judge fit against the matching track section of the profile (the shared core applies to both). Output strictly:
   ```json
   {"track": "engineer" | "management", "score": 0-100, "reasons": ["...", "..."], "gaps": ["..."]}
   ```
   Scoring guide:
   - 90+: stack, level, location and salary all line up; would be a strong application
   - 75 to 89: clear fit with one soft gap (a tool not used in a while, salary unstated, hybrid days unclear)
   - 50 to 74: plausible but a real gap (level mismatch, half the stack unfamiliar, commute borderline)
   - below 50: not worth the energy
   Reasons: two short sentences, specific to this role and this profile, written so they read well on a phone card. Gaps: things to address in a cover note, or empty.
   Score fit, not "will I get it". Do not penalise unstated salary; note it as a gap.
   The queue also carries `dismissals`: what Steve has rejected recently, grouped by reason (location, salary, level, stack, sector, agency, hours, other) with examples. Treat these as calibration: a role that closely resembles a dismissed pattern (same reason would apply) scores lower and the first reason names the resemblance, e.g. "Similar to three IT Manager roles dismissed as too junior". Do not let a single dismissal swing everything; three or more of one reason is a pattern.
   If a role has `watch: 1` it is from a company on Steve's watchlist. Do not inflate the score; the app already notifies at a lower bar for these. Do mention in reasons that it is a target employer.
   If a role has `partial_ad: true`, the description is a stub or cut off (`partial_reason` says why). Score what can be seen but cap the score at 70 and add the gap "Scored on a partial ad" so it never triggers a notification on incomplete information.

3. The wrapper generates a run id (`YYMMDD-HHMM-<4 hex>`) per pass and sends it as `run_id` at the top level of the batch. Output the whole batch as ONE JSON document on stdout and nothing else:
   ```json
   {"scores": [{"role_id": 123, "track": "engineer", "score": 88, "reasons": [...], "gaps": [...], "model": "<model name>"}, ...]}
   ```
   The wrapper script submits it with `curl -s -X POST $CAREER_URL/api/scores/batch -H 'content-type: application/json' --data @-`.
   The agent needs no curl, no Write, no scratch files. The app handles notifications; never post to Discord per role.

4. The wrapper logs one line from the response: `run <run_id>: scored N roles [ids], M above threshold`. `GET /api/scores/recent?run_id=<run_id>` shows exactly what that pass wrote. Never report counts of low scores or rejections anywhere Steve reads.

## Failure handling

- Network error on the GET: retry once after 60 seconds, then stop quietly and let the next run pick it up.
- A single role that fails to score: skip it; it stays in the queue.
- Never mark roles applied, dismissed, or any other status. Scoring only.
