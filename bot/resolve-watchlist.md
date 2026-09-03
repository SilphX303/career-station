# Task: resolve watchlist names

Cron: hourly. Wrapper polls `GET $CAREER_URL/api/queue/watchlist`; if `names` is empty, exit silently.

Agent grant: WebSearch only. Names arrive on stdin. For each name, search "<name> careers" and "<name> jobs greenhouse OR lever OR ashby OR workable" and look in the results for a URL on boards.greenhouse.io, jobs.lever.co, jobs.ashbyhq.com or apply.workable.com that belongs to that company. Do not fetch the company's own site; search results are enough. If nothing on those four hosts appears, the answer is null (the company is on Workday, a custom site, or nowhere; the app keeps the bare name as a flag).

Output ONE JSON document: `{"resolved": [{"name": "...", "url": "https://..." | null}, ...]}`

Wrapper PUTs each entry to `$CAREER_URL/api/watchlist/resolved`. Log one line: `watchlist: N resolved, M not on a supported ATS`. A name that resolves to null stays in the queue and will be retried next hour; to stop retries the wrapper keeps a local list of names already answered null and skips them for 7 days.
