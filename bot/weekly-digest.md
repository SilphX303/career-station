# Task: weekly digest

Cron: Monday 10:00 Europe/London (`0 10 * * 1`). Wrapper only; no agent needed.

1. `GET $CAREER_URL/api/digest?days=7`
2. Post to the Discord webhook (`CAREER_DISCORD_WEBHOOK`, same one the app uses) a message shaped like:

```
career-station, week to Mon 8 Sep
Found 41 new roles, 6 cleared the bar. 5 briefs, 3 documents drafted.
Moved: 4 shortlisted, 3 applied, 1 progressing.
In flight now: 2 shortlisted, 5 applied, 2 progressing.
Top this week:
  72  Director of IT & Information Security, Thesis (new)
  72  IAM Engineer, Methods (shortlisted)
  ...
Closed this week: 3.
```

Rules:
- "Closed this week" is `moved.rejected + moved.declined` as a single number. Never list rejected roles, never show a ratio, never show a running total of rejections.
- If `found` is 0 and nothing moved, post one line: "career-station: quiet week, nothing new." Do not skip the post; silence looks like a broken job.
- Log one line: `digest posted` or `digest failed: <reason>`.
