# Task: research a role's employer

Runs on ark-agent-01. Wrapper polls `GET $CAREER_URL/api/queue/research?limit=3` every 15 minutes; Claude is invoked only when the queue is non-empty. Roles at or above the notify threshold are queued automatically when scored; Steve can also request one from the sheet.

Agent grant: WebSearch and WebFetch only. No Bash, no Write, no Read. The wrapper does the HTTP to career-station.

## Wrapper

1. GET the queue. If `items` is empty, exit silently.
2. Pass the JSON to the agent on stdin.
3. Agent prints ONE JSON document: `{"briefs": [{"role_id": N, "status": "ready", "brief": {...}, "model": "<model>"}, ...]}`
4. For each entry, `PUT $CAREER_URL/api/roles/{role_id}/research` with `{"brief", "status", "model"}`. On extraction failure, PUT `{"status":"failed","error":"<first 300 chars>"}` for each item in the batch.
5. Log one line per non-empty batch: `briefed N roles (M failed)`. Cap agent time at 8 minutes per batch.

## Agent instructions

Each item: `id, title, company, location, salary_min, salary_max, url, description, score, gaps, track`. `constraints` carries Steve's salary floor and the things he will not do.

Purpose: help Steve decide whether to apply, not sell him the role. Find the things an ad never says. Be concrete and sourced; say "unknown" rather than guess. If `company` is a recruitment agency, the employer is usually unnamed: research what can be found from the ad text (sector, size, location, clues) and say so in the verdict.

Searches worth running (adapt to what turns up): "<company> glassdoor", "<company> interview process", "<company> reddit", "<company> layoffs 2026", "<company> news", "<company> AI interview" or "HireVue" or "async video interview", "<company> salary <title>", "<company> return to office". WebFetch the Glassdoor or Indeed reviews page and the company careers page when reachable; if a page blocks you, use the search snippets and say the source was a snippet.

Output `brief` with exactly these keys:

```json
{
  "verdict": "Two or three sentences. Whether this looks worth an application and the single most important reason either way.",
  "ai_interview": "yes" | "no" | "unknown",
  "salary_honesty": "Does the advertised range match what people report for this level here? One or two sentences, or 'no data'.",
  "hiring_process": "Stages and rough duration as described by candidates, or 'no data'.",
  "glassdoor": {"rating": 4.1 | null, "reviews": 812 | null, "themes": ["three to five recurring themes, positive and negative, from recent reviews"]},
  "flags": [{"kind": "red" | "amber" | "green", "text": "one specific, sourced observation", "source": "url or 'snippet'"}],
  "stack": ["tools and platforms the employer actually uses, from job ads, engineering blogs, StackShare, reviews"],
  "news": ["two to four dated items from the last 12 months: funding, layoffs, acquisitions, leadership change, office moves"],
  "company": {"size": "headcount band", "sector": "...", "hq": "..."},
  "sources": ["urls you actually used, up to 8"]
}
```

Flag rules:
- `red`: an AI-conducted interview stage; evidence that the advertised range is not paid; layoffs or restructuring in the last 12 months; reviews describing a hybrid pattern that changed after joining; a Glassdoor rating under 3.2 with recent reviews agreeing; a role that has been re-advertised repeatedly.
- `amber`: anything that needs a question at interview rather than a no: heavy on-call, high turnover in the team, an ambiguous reporting line, a location that could become a problem.
- `green`: things that make it a diamond: remote-first confirmed by employees, a reputation for paying the range, a strong engineering culture, IT reporting into someone technical, a leader Steve would learn from.
- Every flag must be something you found, not something you inferred from the ad alone. If you found nothing either way, the flags list can be short.

Never write that a company is bad or good in general; describe what the evidence says and let Steve weigh it. Do not include personal information about named individuals beyond their public role title.
