# Inbox sweep: sync step

Append to the end of the daily inbox sweep, after labels are applied.

For every message the sweep labelled today under Job Search, collect one item per company:

- Applied (a confirmation of an application sent) -> state `applied`
- Progressing (interview, task, call booked, positive recruiter reply) -> state `progressing`, note = the next step and date if known
- Rejected -> state `rejected`
- Declined (Steve turned it down) -> state `declined`

Then run on the Claude Box (arkadia_run_command):

    curl -s -X POST https://career.arkadia.network/api/sync/status \
      -H 'content-type: application/json' \
      -d '{"source":"inbox","items":[{"company":"...","title":"...","state":"...","note":"..."}]}'

Read the response. Anything in `unmatched` is a role career-station has not seen (probably applied via a direct approach). Mention those to Steve in one line so he can add them by hand if he wants; do not list rejections individually in that line, just "2 rejections couldn't be matched" is enough.
