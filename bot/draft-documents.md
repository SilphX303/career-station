# Task: draft requested documents

Runs on ark-agent-01 (Claude Code, Max subscription). Wrapper polls every 10 minutes; Claude is only invoked when the queue is non-empty.

Env: `CAREER_URL` (https://career.arkadia.network)

## Wrapper

1. `GET $CAREER_URL/api/queue/documents?limit=3`. If `items` is empty, exit 0 silently. No log line for empty polls.
2. Pass the JSON to the agent on stdin. Agent has no tools.
3. Agent prints ONE JSON document: `{"documents": [{"document_id": N, "status": "ready", "content": "<markdown>", "model": "<model>"}, ...]}`
4. For each entry, `PUT $CAREER_URL/api/documents/{document_id}` with `{"content", "status", "model"}`. Extract the largest balanced `{...}` containing a `documents` array, same as the scoring wrapper. If extraction fails, PUT `{"status":"failed","content":"<first 500 chars of output>"}` for every item in the batch so the UI shows a retry rather than a stuck "drafting".
5. Log one line per batch: `drafted N documents (M failed)`.

## Agent instructions

Each item gives you: `kind` (cv or cover), `track`, `role` (title, company, location, salary, url, description, score, reasons, gaps), `base_cv` (Steve's real CV for that track, markdown), and the shared `profile`.

### kind = cv

Produce a tailored CV in markdown. Rules:
- Start from `base_cv`. Keep its structure, section order, employers, dates and every factual claim. Do not invent experience, tools, certifications, numbers or outcomes that are not in the base CV or the profile.
- Tailor by reordering and reweighting, not by adding: bring the bullets that match the ad to the top of each role, trim bullets that are irrelevant to this role, and rewrite the profile paragraph so it speaks to this employer and this job in the ad's own vocabulary where it is honest to do so.
- Mirror the ad's terminology for things Steve has actually done (if the ad says "endpoint management" and the CV says "MDM", use both).
- Address each item in `gaps` where the base CV has something relevant to say, even partially; if there is nothing honest to say, leave the gap alone. Do not add a "gaps" section.
- Length: same as or shorter than the base CV. Never longer.
- Keep the contact line exactly as in the base CV.
- Output the CV only. No preamble, no notes, no explanation of changes.

### kind = cover

Produce a cover note in markdown, 180 to 260 words, in Steve's voice as it reads in the base CV and profile: plain, specific, confident, no filler. Structure:
- One line on why this role and this company (from the ad, not generic praise).
- Two short paragraphs mapping his strongest two or three matching points to what the ad asks for, with a concrete example each from the base CV.
- If a gap in `gaps` is worth addressing, one sentence that handles it honestly (adjacent experience, how he closes it), otherwise skip.
- Closing line with availability and a low-key ask for a conversation.
- No salary. No mention of AI interviews. No "I am writing to apply". No exclamation marks.
- Sign-off "Steve Hunter". Output the note only.

### Both kinds

- Never state or imply that a document was AI-generated.
- If `base_cv` is empty, return `status: "failed"` with content "No base CV for track <track> in the profile" so Steve knows what to fix.
- If `role.description` is empty (placeholder or LinkedIn-only role), still draft from title, company and profile, and add a single first line `> Drafted without the full ad text; check it against the posting.` to the document.
