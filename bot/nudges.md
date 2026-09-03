# Task: daily nudges

Cron: 08:30 Europe/London daily. Wrapper only, no agent.

1. `GET $CAREER_URL/api/nudges`
2. For each role in `progressing` with `prep_ready == 0`, `POST $CAREER_URL/api/roles/{id}/documents` with `{"kind":"prep"}`. The drafting job produces the pack within ten minutes.
3. If any of `stale_applied`, `progressing` or `flagged_open` is non-empty, post to the Discord webhook:

```
career-station, morning nudges
Chase: Head of IT at Thesis, applied 12 days, no reply.
Prep: IAM Engineer at Methods, progressing, prep pack ready in the app.
Flagged: Director of IT at Hargreaves Lansdown is shortlisted and the brief found an AI interview stage.
```

One line per item, no counts of rejections anywhere. If everything is empty, post nothing and log `nudges: quiet`. Otherwise log `nudges: N chase, M prep, K flagged`.
