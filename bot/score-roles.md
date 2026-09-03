# Task: score unscored roles

Runs on ark-agent-01 (Claude Code, Max subscription). Schedule: every 4 hours, offset 20 minutes after the crawl, plus on demand.

Env: `CAREER_URL` (e.g. http://career.arkadia.network)

## Steps

1. `GET $CAREER_URL/api/queue/unscored?limit=40`
   Response: `{ "profile": "<markdown>", "threshold": 75, "roles": [ {id, title, company, location, remote_flag, salary_min, salary_max, salary_text, url, description, posted_at}, ... ] }`
   If `roles` is empty, stop.
   If `profile` is empty, stop and post to Discord: "career-station: profile is empty, nothing to score against."

2. For each role, judge fit against the profile. Output strictly:
   ```json
   {"score": 0-100, "reasons": ["...", "..."], "gaps": ["..."]}
   ```
   Scoring guide:
   - 90+: stack, level, location and salary all line up; would be a strong application
   - 75 to 89: clear fit with one soft gap (a tool not used in a while, salary unstated, hybrid days unclear)
   - 50 to 74: plausible but a real gap (level mismatch, half the stack unfamiliar, commute borderline)
   - below 50: not worth the energy
   Reasons: two short sentences, specific to this role and this profile, written so they read well on a phone card. Gaps: things to address in a cover note, or empty.
   Score fit, not "will I get it". Do not penalise unstated salary; note it as a gap.

3. `PUT $CAREER_URL/api/roles/{id}/score` with the JSON above plus `"model": "<model name>"`.
   The app handles notifications; do not post to Discord per role.

4. After the batch, log one line: `scored N roles, M above threshold`. Nothing else. Never report counts of low scores or rejections anywhere Steve reads.

## Failure handling

- Network error on the GET: retry once after 60 seconds, then stop quietly and let the next run pick it up.
- A single role that fails to score: skip it; it stays in the queue.
- Never mark roles applied, dismissed, or any other status. Scoring only.
