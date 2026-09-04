# Task: read screenshots and pasted ads into roles

Runs on ark-agent-01. Wrapper polls `GET $CAREER_URL/api/queue/ingest?limit=3` every 10 minutes; exits silently when empty.

## Wrapper

1. For each item with images, download each name from `GET $CAREER_URL/api/ingest/image/{name}` into a fresh per-run directory under the ingest scratch root (e.g. `/opt/arkadia/scratch/ingest/<run-id>/`). Delete the directory after the PUT, success or failure.
2. Invoke the agent with the grant `Read(<that directory>/*)` only. No Bash, no Write, no web. Pass the item JSON on stdin with the local image paths substituted in.
3. Agent prints ONE JSON document: `{"roles": [{"ingest_id": N, "status": "ready", "title": ..., "company": ..., "location": ..., "remote": true|false|null, "salary_min": int|null, "salary_max": int|null, "salary_text": str|null, "description": ..., "url": str|null, "model": "<model>"}, ...]}`
4. `PUT $CAREER_URL/api/ingest/{ingest_id}` with each entry. On extraction failure, PUT `{"status":"failed","error":"<first 300 chars>"}` for each item in the batch.
5. Log one line per non-empty batch: `ingest: N read, M failed`.

## Agent instructions

Each item is a job ad Steve captured by hand because the crawl could not reach it: one or more screenshots (read them in order; they are one ad), and/or pasted text, and maybe a URL.

Extract, and only from what is visible:
- `title`: the role title as written.
- `company`: the employer as written. If it is clearly an agency posting, still put the agency name here; do not guess the end employer.
- `location` and `remote`: as written. "Hybrid" is not remote; put the pattern in location ("London, hybrid 2 days").
- `salary_min`, `salary_max` in GBP integers when a figure or range is shown; `salary_text` for anything else ("competitive", "DOE", "€70k", "per day rates").
- `description`: the full ad body as plain text, in reading order, with section headings kept as lines. Do not summarise; the scoring and drafting jobs need the whole thing. If a screenshot is cut off mid-sentence, end where it ends.
- `url`: only if one is visible in the image or given.

If the images are not a job ad, or are unreadable, return `status: "failed"` with a one-line reason. Do not invent any field. Do not add commentary in the description.
