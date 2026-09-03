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

Read the response. `matched` are updates to roles the app already had. `created` are applied or progressing roles the app had never seen (direct approaches, agency postings); it has recorded them so the pipeline is complete. `unmatched` are rejections or declines it could not place; report those as a count only.
