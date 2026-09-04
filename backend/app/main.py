import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import cluster, crawl, db, fulltext, notify, render, sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
STATIC = Path(__file__).resolve().parent.parent / "static"
STATES = {"new", "shortlisted", "applied", "progressing", "rejected", "declined", "dismissed"}
CRAWL_HOURS = int(os.environ.get("CAREER_CRAWL_HOURS", "4"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    sched = AsyncIOScheduler(timezone="Europe/London")
    sched.add_job(crawl.run_all, "interval", hours=CRAWL_HOURS, id="crawl")
    sched.start()
    yield
    sched.shutdown(wait=False)


app = FastAPI(title="career-station", lifespan=lifespan)


REASONS = {"location", "salary", "level", "stack", "sector", "agency", "hours", "other"}


class StatusIn(BaseModel):
    state: str
    note: str | None = None
    reason: str | None = None


class ScoreIn(BaseModel):
    score: int
    reasons: list[str] = []
    gaps: list[str] = []
    model: str | None = None
    track: str | None = None


class BatchScore(ScoreIn):
    role_id: int


class BatchIn(BaseModel):
    scores: list[BatchScore]


class SyncItem(BaseModel):
    company: str
    title: str | None = None
    state: str
    note: str | None = None


class SyncIn(BaseModel):
    items: list[SyncItem]
    source: str = "inbox"


class BriefResult(BaseModel):
    brief: dict | None = None
    status: str = "ready"  # ready | failed
    model: str | None = None
    error: str | None = None


class DocRequest(BaseModel):
    kind: str  # cv | cover


class DocResult(BaseModel):
    content: str
    status: str = "ready"  # ready | failed
    model: str | None = None


class ProfileIn(BaseModel):
    markdown: str | None = None
    cv_engineer: str | None = None
    cv_management: str | None = None
    watchlist: list[str] | None = None
    search_terms: list[str] | None = None
    filters: dict | None = None
    threshold: int | None = None


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/roles")
def list_roles(state: str | None = None, limit: int = 200):
    con = db.connect()
    q = """SELECT r.id, r.title, r.company, r.location, r.remote_flag, r.salary_min, r.salary_max, r.salary_text,
                  r.url, r.posted_at, r.first_seen, r.filtered, r.filter_reason, r.desc_quality, r.watch, s.name AS source,
                  sc.score, sc.reasons, sc.track, st.state,
                  (SELECT status FROM documents d WHERE d.role_id=r.id AND d.kind='cv' ORDER BY d.id DESC LIMIT 1) AS doc_cv,
                  (SELECT status FROM documents d WHERE d.role_id=r.id AND d.kind='cover' ORDER BY d.id DESC LIMIT 1) AS doc_cover,
                  (SELECT status FROM documents d WHERE d.role_id=r.id AND d.kind='prep' ORDER BY d.id DESC LIMIT 1) AS doc_prep,
                  rs.status AS brief_status, rs.brief AS brief_json,
                  (SELECT COUNT(*) FROM roles m WHERE m.cluster_id = r.id) AS cluster_size
           FROM roles r
           LEFT JOIN research rs ON rs.role_id = r.id
           JOIN sources s ON s.id = r.source_id
           LEFT JOIN scores sc ON sc.role_id = r.id
           LEFT JOIN status st ON st.role_id = r.id
           WHERE 1=1"""
    args: list = []
    q += " AND r.cluster_id IS NULL"
    if state == "filtered":
        q += " AND r.filtered = 1"
    elif state:
        q += " AND r.filtered = 0 AND st.state = ?"
        args.append(state)
    else:
        q += " AND r.filtered = 0 AND (st.state IS NULL OR st.state IN ('new','shortlisted'))"
    q += " ORDER BY COALESCE(sc.score, -1) DESC, r.first_seen DESC LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in con.execute(q, args)]
    for r in rows:
        r["reasons"] = json.loads(r["reasons"]) if r.get("reasons") else []
        b = json.loads(r.pop("brief_json")) if r.get("brief_json") else None
        r["red_flags"] = sum(1 for f in (b or {}).get("flags", []) if f.get("kind") == "red")
        r["ai_interview"] = (b or {}).get("ai_interview")
    con.close()
    return rows


@app.get("/api/roles/{role_id}")
def get_role(role_id: int):
    con = db.connect()
    r = con.execute(
        """SELECT r.*, s.name AS source, sc.score, sc.reasons, sc.gaps, sc.track, st.state, st.note
           FROM roles r JOIN sources s ON s.id=r.source_id
           LEFT JOIN scores sc ON sc.role_id=r.id LEFT JOIN status st ON st.role_id=r.id
           WHERE r.id=?""", (role_id,)).fetchone()
    con.close()
    if not r:
        raise HTTPException(404)
    d = dict(r)
    d["reasons"] = json.loads(d["reasons"]) if d.get("reasons") else []
    d["gaps"] = json.loads(d["gaps"]) if d.get("gaps") else []
    q, why = fulltext.assess(d.get("description"))
    d["truncated"] = q == "partial" and bool(d.get("url"))
    d["desc_reason"] = why
    con2 = db.connect()
    ing = con2.execute("SELECT images FROM ingest WHERE role_id=?", (role_id,)).fetchone()
    d["screenshots"] = json.loads(ing["images"]) if ing else []
    head = d["cluster_id"] or role_id
    d["also_posted"] = [dict(m) for m in con2.execute(
        """SELECT r.id, r.company, r.url, r.salary_min, r.salary_max, r.location, r.first_seen, s.name AS source
           FROM roles r JOIN sources s ON s.id=r.source_id WHERE (r.cluster_id = ? OR r.id = ?) AND r.id != ? ORDER BY r.first_seen""",
        (head, head, role_id))]
    con2.close()
    return d


@app.put("/api/roles/{role_id}/status")
def set_status(role_id: int, body: StatusIn):
    if body.state not in STATES:
        raise HTTPException(400, f"state must be one of {sorted(STATES)}")
    con = db.connect()
    if not con.execute("SELECT 1 FROM roles WHERE id=?", (role_id,)).fetchone():
        con.close()
        raise HTTPException(404)
    if body.reason and body.reason not in REASONS:
        raise HTTPException(400, f"reason must be one of {sorted(REASONS)}")
    with con:
        con.execute(
            """INSERT INTO status (role_id, state, changed_at, note, reason) VALUES (?,?,?,?,?)
               ON CONFLICT(role_id) DO UPDATE SET state=excluded.state, changed_at=excluded.changed_at,
               note=excluded.note, reason=excluded.reason""",
            (role_id, body.state, db.now(), body.note, body.reason),
        )
    con.close()
    return {"ok": True, "state": body.state}


def dismissal_patterns(con, limit: int = 40) -> dict:
    """What Steve has been saying no to, for the scoring bot and the Profile page."""
    rows = con.execute(
        """SELECT st.reason, st.note, r.title, r.company, r.location, r.salary_max, sc.score, sc.track
           FROM status st JOIN roles r ON r.id=st.role_id LEFT JOIN scores sc ON sc.role_id=r.id
           WHERE st.state IN ('dismissed','declined') AND st.reason IS NOT NULL
           ORDER BY st.changed_at DESC LIMIT ?""", (limit,)).fetchall()
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["reason"], []).append({
            "title": r["title"], "company": r["company"], "location": r["location"],
            "salary_max": r["salary_max"], "score": r["score"], "track": r["track"], "note": r["note"]})
    return {"total": len(rows), "by_reason": {k: {"count": len(v), "examples": v[:5]} for k, v in by.items()}}


@app.get("/api/queue/unscored")
def queue_unscored(limit: int = 40):
    """For the scoring bot: roles that passed filters and have no score yet. Includes the profile."""
    con = db.connect()
    prof = get_profile()
    rows = [dict(r) for r in con.execute(
        """SELECT r.id, r.title, r.company, r.location, r.remote_flag, r.salary_min, r.salary_max, r.salary_text,
                  r.url, r.description, r.posted_at, r.desc_quality, r.desc_reason, r.watch
           FROM roles r LEFT JOIN scores sc ON sc.role_id = r.id LEFT JOIN status st ON st.role_id = r.id
           WHERE r.filtered = 0 AND sc.role_id IS NULL AND r.cluster_id IS NULL
             AND (st.state IS NULL OR st.state NOT IN ('dismissed','rejected','declined'))
           ORDER BY r.first_seen DESC LIMIT ?""", (limit,))]
    for r in rows:
        r["partial_ad"] = r.pop("desc_quality") == "partial"
        r["partial_reason"] = r.pop("desc_reason")
    patterns = dismissal_patterns(con)
    con.close()
    return {"profile": prof["markdown"], "threshold": prof["threshold"], "dismissals": patterns, "roles": rows}


@app.put("/api/roles/{role_id}/score")
async def put_score(role_id: int, body: ScoreIn):
    if not 0 <= body.score <= 100:
        raise HTTPException(400, "score must be 0 to 100")
    con = db.connect()
    role = con.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
    if not role:
        con.close()
        raise HTTPException(404)
    thr = con.execute("SELECT threshold FROM profile WHERE id=1").fetchone()["threshold"]
    if role["watch"]:
        thr = max(0, thr - 10)
    with con:
        con.execute(
            """INSERT INTO scores (role_id, score, reasons, gaps, scored_at, model, track) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(role_id) DO UPDATE SET score=excluded.score, reasons=excluded.reasons,
               gaps=excluded.gaps, scored_at=excluded.scored_at, model=excluded.model, track=excluded.track""",
            (role_id, body.score, json.dumps(body.reasons), json.dumps(body.gaps), db.now(), body.model, body.track),
        )
    notified = False
    if body.score >= thr:
        with con:
            con.execute("INSERT OR IGNORE INTO research (role_id, status, requested_at) VALUES (?, 'pending', ?)", (role_id, db.now()))
    if body.score >= thr and not con.execute(
        "SELECT 1 FROM notifications WHERE role_id=? AND channel='discord'", (role_id,)).fetchone():
        if await notify.discord(dict(role), body.score, body.reasons):
            with con:
                con.execute("INSERT INTO notifications (role_id, channel, sent_at) VALUES (?, 'discord', ?)",
                            (role_id, db.now()))
            notified = True
    con.close()
    return {"ok": True, "notified": notified}


@app.post("/api/scores/batch")
async def post_scores_batch(body: BatchIn):
    """Bot submits a whole batch in one call. Each item is scored independently; bad ones are reported, not fatal."""
    ok, failed, notified, above = [], [], 0, 0
    con = db.connect()
    thr = con.execute("SELECT threshold FROM profile WHERE id=1").fetchone()["threshold"]
    con.close()
    for item in body.scores:
        try:
            r = await put_score(item.role_id, ScoreIn(**item.model_dump(exclude={"role_id"})))
            ok.append(item.role_id)
            notified += int(bool(r.get("notified")))
            above += int(item.score >= thr)
        except HTTPException as e:
            failed.append({"role_id": item.role_id, "why": e.detail})
    return {"scored": len(ok), "above_threshold": above, "failed": failed, "notified": notified}


@app.post("/api/sync/status")
def sync_status(body: SyncIn):
    """Inbox sweep posts what it found. Fuzzy-matches to roles and updates status. Never downgrades progressing to applied."""
    order = {"new": 0, "shortlisted": 1, "applied": 2, "progressing": 3, "rejected": 4, "declined": 4, "dismissed": 4}
    con = db.connect()
    roles = [dict(r) for r in con.execute(
        "SELECT r.id, r.company, r.title, st.state FROM roles r LEFT JOIN status st ON st.role_id=r.id")]
    matched, unmatched, created = [], [], []
    ts = db.now()
    with con:
        for it in body.items:
            if it.state not in STATES:
                unmatched.append({**it.model_dump(), "why": "bad state"})
                continue
            role, conf = sync.best_match(it.company, it.title, roles)
            if not role and it.state in ("applied", "progressing"):
                role = _placeholder_role(con, it, body.source, ts)
                roles.append(role)
                created.append({"role_id": role["id"], "title": role["title"], "company": role["company"], "state": it.state})
                conf = 1.0
            if not role:
                unmatched.append({**it.model_dump(), "why": f"no match ({conf:.2f})"})
                continue
            cur = role.get("state") or "new"
            if order.get(it.state, 0) < order.get(cur, 0) and cur in ("progressing", "rejected", "declined"):
                matched.append({"role_id": role["id"], "title": role["title"], "kept": cur, "confidence": round(conf, 2)})
                continue
            note = f"[{body.source}] {it.note}" if it.note else f"[{body.source}]"
            con.execute(
                """INSERT INTO status (role_id, state, changed_at, note) VALUES (?,?,?,?)
                   ON CONFLICT(role_id) DO UPDATE SET state=excluded.state, changed_at=excluded.changed_at, note=excluded.note""",
                (role["id"], it.state, ts, note))
            role["state"] = it.state
            matched.append({"role_id": role["id"], "title": role["title"], "state": it.state, "confidence": round(conf, 2)})
    con.close()
    return {"matched": matched, "created": created, "unmatched": unmatched}


def _placeholder_role(con, it: "SyncItem", source: str, ts: str) -> dict:
    """An application made outside the app (direct approach, agency). Record it so the pipeline is complete."""
    con.execute("INSERT OR IGNORE INTO sources (name, kind, enabled) VALUES (?, 'manual', 0)", (source,))
    sid = con.execute("SELECT id FROM sources WHERE name=?", (source,)).fetchone()["id"]
    title = it.title or "Role (title unknown)"
    import hashlib
    h = hashlib.sha1(f"{source}|{it.company}|{title}|{ts}".encode()).hexdigest()
    cur = con.execute(
        """INSERT INTO roles (source_id, external_id, url, title, company, location, remote_flag,
           first_seen, last_seen, hash, filtered) VALUES (?,?,?,?,?,?,0,?,?,?,0)""",
        (sid, None, "", title, it.company, None, ts, ts, h))
    return {"id": cur.lastrowid, "company": it.company, "title": title, "state": None}


@app.post("/api/roles/{role_id}/research")
def request_research(role_id: int):
    con = db.connect()
    if not con.execute("SELECT 1 FROM roles WHERE id=?", (role_id,)).fetchone():
        con.close()
        raise HTTPException(404)
    with con:
        con.execute(
            """INSERT INTO research (role_id, status, requested_at) VALUES (?, 'pending', ?)
               ON CONFLICT(role_id) DO UPDATE SET status='pending', requested_at=excluded.requested_at, brief=NULL""",
            (role_id, db.now()))
    con.close()
    return {"ok": True, "status": "pending"}


@app.get("/api/roles/{role_id}/research")
def get_research(role_id: int):
    con = db.connect()
    r = con.execute("SELECT * FROM research WHERE role_id=?", (role_id,)).fetchone()
    con.close()
    if not r:
        return None
    d = dict(r)
    d["brief"] = json.loads(d["brief"]) if d.get("brief") else None
    return d


@app.get("/api/queue/research")
def queue_research(limit: int = 3):
    """For the research bot: pending briefs with the role and what the profile cares about."""
    con = db.connect()
    prof = get_profile()
    items = []
    for rs in con.execute("SELECT role_id FROM research WHERE status='pending' ORDER BY requested_at LIMIT ?", (limit,)):
        r = con.execute(
            """SELECT r.id, r.title, r.company, r.location, r.salary_min, r.salary_max, r.url, r.description,
                      sc.score, sc.gaps, sc.track FROM roles r LEFT JOIN scores sc ON sc.role_id=r.id WHERE r.id=?""",
            (rs["role_id"],)).fetchone()
        role = dict(r)
        role["gaps"] = json.loads(role["gaps"]) if role.get("gaps") else []
        role["description"] = (role["description"] or "")[:3000]
        items.append(role)
    con.close()
    filt = prof["filters"]
    return {"constraints": {"salary_floor": filt.get("salary_floor"), "will_not": ["AI-conducted interviews", "pure service desk", "contract under 6 months"]}, "items": items}


@app.put("/api/roles/{role_id}/research")
def put_research(role_id: int, body: BriefResult):
    if body.status not in ("ready", "failed"):
        raise HTTPException(400, "status must be ready or failed")
    con = db.connect()
    if not con.execute("SELECT 1 FROM research WHERE role_id=?", (role_id,)).fetchone():
        con.close()
        raise HTTPException(404)
    payload = body.brief if body.status == "ready" else {"error": body.error or "research failed"}
    with con:
        con.execute("UPDATE research SET brief=?, status=?, generated_at=?, model=? WHERE role_id=?",
                    (json.dumps(payload), body.status, db.now(), body.model, role_id))
    con.close()
    return {"ok": True}


DOC_KINDS = {"cv", "cover", "prep"}


@app.post("/api/roles/{role_id}/documents")
def request_document(role_id: int, body: DocRequest):
    if body.kind not in DOC_KINDS:
        raise HTTPException(400, "kind must be cv or cover")
    con = db.connect()
    if not con.execute("SELECT 1 FROM roles WHERE id=?", (role_id,)).fetchone():
        con.close()
        raise HTTPException(404)
    pending = con.execute("SELECT id FROM documents WHERE role_id=? AND kind=? AND status='pending'", (role_id, body.kind)).fetchone()
    if pending:
        con.close()
        return {"id": pending["id"], "status": "pending", "already": True}
    with con:
        cur = con.execute("INSERT INTO documents (role_id, kind, status, requested_at) VALUES (?,?,'pending',?)", (role_id, body.kind, db.now()))
    con.close()
    return {"id": cur.lastrowid, "status": "pending"}


@app.get("/api/roles/{role_id}/documents")
def list_documents(role_id: int):
    con = db.connect()
    rows = [dict(r) for r in con.execute(
        "SELECT id, kind, status, content, requested_at, generated_at, model FROM documents WHERE role_id=? ORDER BY id DESC", (role_id,))]
    con.close()
    return rows


class DocEdit(BaseModel):
    content: str


@app.patch("/api/documents/{doc_id}")
def edit_document(doc_id: int, body: DocEdit):
    """Steve's own edit of a ready document. Keeps status ready; PDF renders from the stored content."""
    if not body.content.strip():
        raise HTTPException(400, "content is empty")
    con = db.connect()
    d = con.execute("SELECT status FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not d:
        con.close()
        raise HTTPException(404)
    if d["status"] != "ready":
        con.close()
        raise HTTPException(409, "only ready documents can be edited")
    with con:
        con.execute("UPDATE documents SET content=?, model=COALESCE(model,'') || ' +edited' WHERE id=? AND model NOT LIKE '%+edited'", (body.content, doc_id))
        con.execute("UPDATE documents SET content=? WHERE id=?", (body.content, doc_id))
    con.close()
    return {"ok": True}


@app.get("/api/documents/{doc_id}.pdf")
def document_pdf(doc_id: int):
    con = db.connect()
    d = con.execute(
        """SELECT d.kind, d.status, d.content, r.company, r.title FROM documents d JOIN roles r ON r.id=d.role_id WHERE d.id=?""",
        (doc_id,)).fetchone()
    con.close()
    if not d:
        raise HTTPException(404)
    if d["status"] != "ready" or not d["content"]:
        raise HTTPException(409, "document not ready")
    pdf = render.to_pdf(d["content"])
    name = render.filename(d["kind"], d["company"], d["title"])
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/queue/documents")
def queue_documents(limit: int = 5):
    """For the drafting bot. Each item carries everything needed: role, ad, score, profile, base CV for the track."""
    con = db.connect()
    prof = get_profile()
    items = []
    for d in con.execute("SELECT * FROM documents WHERE status='pending' ORDER BY requested_at LIMIT ?", (limit,)):
        r = con.execute(
            """SELECT r.id, r.title, r.company, r.location, r.remote_flag, r.salary_min, r.salary_max, r.url, r.description,
                      sc.score, sc.reasons, sc.gaps, sc.track FROM roles r
               LEFT JOIN scores sc ON sc.role_id=r.id WHERE r.id=?""", (d["role_id"],)).fetchone()
        role = dict(r)
        role["reasons"] = json.loads(role["reasons"]) if role.get("reasons") else []
        role["gaps"] = json.loads(role["gaps"]) if role.get("gaps") else []
        track = role.get("track") or "engineer"
        rs = con.execute("SELECT brief, status FROM research WHERE role_id=?", (d["role_id"],)).fetchone()
        st = con.execute("SELECT note FROM status WHERE role_id=?", (d["role_id"],)).fetchone()
        items.append({
            "document_id": d["id"], "kind": d["kind"], "track": track, "role": role,
            "base_cv": prof["cv_management"] if track == "management" else prof["cv_engineer"],
            "brief": json.loads(rs["brief"]) if rs and rs["status"] == "ready" and rs["brief"] else None,
            "pipeline_note": st["note"] if st else None,
        })
    con.close()
    return {"profile": prof["markdown"], "items": items}


@app.put("/api/documents/{doc_id}")
def put_document(doc_id: int, body: DocResult):
    if body.status not in ("ready", "failed"):
        raise HTTPException(400, "status must be ready or failed")
    con = db.connect()
    if not con.execute("SELECT 1 FROM documents WHERE id=?", (doc_id,)).fetchone():
        con.close()
        raise HTTPException(404)
    with con:
        con.execute("UPDATE documents SET content=?, status=?, generated_at=?, model=? WHERE id=?",
                    (body.content, body.status, db.now(), body.model, doc_id))
    con.close()
    return {"ok": True}


@app.post("/api/roles/{role_id}/description")
async def load_description(role_id: int):
    """Fetch the full ad on demand."""
    con = db.connect()
    r = con.execute("SELECT r.id, r.external_id, r.url, r.description, s.name AS source FROM roles r JOIN sources s ON s.id=r.source_id WHERE r.id=?", (role_id,)).fetchone()
    if not r:
        con.close()
        raise HTTPException(404)
    result = await crawl.fill_descriptions(con, [(r["id"], r["source"], r["external_id"], r["url"])], dict(os.environ), cap=1)
    desc = con.execute("SELECT description FROM roles WHERE id=?", (role_id,)).fetchone()["description"]
    q, why = fulltext.assess(desc)
    with con:
        con.execute("UPDATE roles SET desc_quality=?, desc_reason=? WHERE id=?", (q, why, role_id))
    con.close()
    return {"ok": result["filled"] == 1, "description": desc, "truncated": q == "partial", "reason": why}


@app.delete("/api/roles/{role_id}/score")
def rescore(role_id: int):
    """Drop the score so the bot picks the role up again (e.g. after the full ad was loaded)."""
    con = db.connect()
    with con:
        con.execute("DELETE FROM scores WHERE role_id=?", (role_id,))
    con.close()
    return {"ok": True}


@app.get("/api/digest")
def digest(days: int = 7):
    """Numbers for the weekly digest. Rejections are a count only, by design."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    con = db.connect()
    def one(q, *a):
        return con.execute(q, a).fetchone()[0]
    found = one("SELECT COUNT(*) FROM roles WHERE first_seen >= ? AND filtered = 0", since)
    above = one("SELECT COUNT(*) FROM scores sc JOIN profile p ON p.id=1 WHERE sc.scored_at >= ? AND sc.score >= p.threshold", since)
    moved = {st: one("SELECT COUNT(*) FROM status WHERE changed_at >= ? AND state=?", since, st)
             for st in ("shortlisted", "applied", "progressing", "rejected", "declined")}
    open_now = {st: one("SELECT COUNT(*) FROM status WHERE state=?", st) for st in ("shortlisted", "applied", "progressing")}
    top = [dict(r) for r in con.execute(
        """SELECT r.id, r.title, r.company, sc.score, st.state FROM scores sc JOIN roles r ON r.id=sc.role_id
           LEFT JOIN status st ON st.role_id=r.id JOIN profile p ON p.id=1
           WHERE sc.scored_at >= ? AND sc.score >= p.threshold AND r.filtered = 0 ORDER BY sc.score DESC LIMIT 5""", (since,))]
    briefs = one("SELECT COUNT(*) FROM research WHERE status='ready' AND generated_at >= ?", since)
    docs = one("SELECT COUNT(*) FROM documents WHERE status='ready' AND generated_at >= ?", since)
    con.close()
    return {"since": since, "found": found, "above_threshold": above, "moved": moved, "open": open_now,
            "top": top, "briefs": briefs, "documents": docs}


class ResolveIn(BaseModel):
    names: list[str] | None = None  # default: every bare-name entry in the watchlist


@app.post("/api/watchlist/resolve")
async def watchlist_resolve(body: ResolveIn | None = None):
    """Try the public ATS feeds for bare-name watchlist entries and rewrite the ones that resolve."""
    from .sources.watchlist import parse_entry, resolve_feed
    prof = get_profile()
    entries = prof["watchlist"]
    targets = set(body.names) if body and body.names else {e for e in entries if not parse_entry(e)["ats"]}
    resolved, unresolved, out = [], [], []
    for e in entries:
        pe = parse_entry(e)
        if e in targets and not pe["ats"]:
            url = await resolve_feed(pe["name"], dict(os.environ))
            if url:
                out.append(f"{pe['name']} {url}")
                resolved.append({"name": pe["name"], "url": url})
                continue
            unresolved.append(pe["name"])
        out.append(e)
    if resolved:
        put_profile(ProfileIn(watchlist=out))
    return {"resolved": resolved, "unresolved": unresolved, "watchlist": out}


@app.get("/api/queue/watchlist")
def queue_watchlist():
    """Bare names the app could not resolve itself; the research bot can look them up by web search."""
    from .sources.watchlist import parse_entry
    entries = get_profile()["watchlist"]
    return {"names": [parse_entry(e)["name"] for e in entries if not parse_entry(e)["ats"]]}


class WatchResolved(BaseModel):
    name: str
    url: str | None


@app.put("/api/watchlist/resolved")
def watchlist_resolved(body: WatchResolved):
    """Bot hands back a careers URL for a bare name (or null if none exists on a supported ATS)."""
    from .sources.watchlist import parse_entry
    if not body.url:
        return {"ok": True, "changed": False}
    if not parse_entry(body.url)["ats"]:
        raise HTTPException(400, "url is not on a supported ATS")
    entries = get_profile()["watchlist"]
    out, changed = [], False
    for e in entries:
        pe = parse_entry(e)
        if not pe["ats"] and pe["name"].strip().lower() == body.name.strip().lower():
            out.append(f"{pe['name']} {body.url}"); changed = True
        else:
            out.append(e)
    if changed:
        put_profile(ProfileIn(watchlist=out))
    return {"ok": True, "changed": changed}


@app.post("/api/cluster")
def cluster_now():
    con = db.connect()
    out = cluster.run(con)
    con.close()
    return out


INGEST_DIR = db.DATA_DIR / "ingest"
ALLOWED_IMG = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


class IngestResult(BaseModel):
    status: str = "ready"  # ready | failed
    title: str | None = None
    company: str | None = None
    location: str | None = None
    remote: bool | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_text: str | None = None
    description: str | None = None
    url: str | None = None
    error: str | None = None
    model: str | None = None


def _create_manual_role(con, fields: dict, source_name: str, images: list[str]) -> int:
    import hashlib
    import json as _json
    from . import filters as _filters, fulltext as _fulltext
    prof = con.execute("SELECT filters FROM profile WHERE id=1").fetchone()
    filt = _json.loads(prof["filters"]) if prof else {}
    con.execute("INSERT OR IGNORE INTO sources (name, kind, enabled) VALUES (?, 'manual', 0)", (source_name,))
    sid = con.execute("SELECT id FROM sources WHERE name=?", (source_name,)).fetchone()["id"]
    ts = db.now()
    title = fields.get("title") or "Role (title unknown)"
    company = fields.get("company")
    loc = fields.get("location")
    desc = fields.get("description") or ""
    remote = bool(fields.get("remote")) or "remote" in f"{loc or ''} {desc}".lower()
    role = {"title": title, "description": desc, "location": loc, "remote_flag": remote,
            "salary_min": fields.get("salary_min"), "salary_max": fields.get("salary_max")}
    fl, why = _filters.apply(role, filt)
    dq, dr = _fulltext.assess(desc)
    h = hashlib.sha1(f"{source_name}|{company}|{title}|{loc}|{ts}".encode()).hexdigest()
    cur = con.execute(
        """INSERT INTO roles (source_id, external_id, url, title, company, location, remote_flag, salary_min, salary_max, salary_text,
           description, posted_at, first_seen, last_seen, hash, filtered, filter_reason, desc_quality, desc_reason)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, None, fields.get("url") or "", title, company, loc, int(remote), fields.get("salary_min"), fields.get("salary_max"),
         fields.get("salary_text"), desc, None, ts, ts, h, int(fl), why, dq, dr))
    rid = cur.lastrowid
    con.execute("INSERT OR IGNORE INTO status (role_id, state, changed_at, note) VALUES (?, 'new', ?, ?)",
                (rid, ts, "[screenshot] " + ", ".join(images) if images else None))
    return rid


@app.post("/api/ingest")
async def ingest(text: str | None = Form(None), url: str | None = Form(None), files: list[UploadFile] = File(default=[])):
    """Add a role by hand: screenshots (bot reads them), pasted ad text, or both. URL optional."""
    imgs = []
    INGEST_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        ext = ALLOWED_IMG.get(f.content_type or "")
        if not ext:
            raise HTTPException(400, f"unsupported image type {f.content_type}")
        data = await f.read()
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(400, "image over 8 MB")
        import secrets
        name = f"{db.now()[:10]}-{secrets.token_hex(4)}{ext}".replace(":", "")
        (INGEST_DIR / name).write_bytes(data)
        imgs.append(name)
    if not imgs and not (text and text.strip()):
        raise HTTPException(400, "give me a screenshot or some ad text")
    con = db.connect()
    with con:
        cur = con.execute(
            "INSERT INTO ingest (status, kind, text, url, images, requested_at) VALUES ('pending', ?, ?, ?, ?, ?)",
            ("image" if imgs else "text", text, url, json.dumps(imgs), db.now()))
    con.close()
    return {"id": cur.lastrowid, "status": "pending", "images": len(imgs)}


@app.get("/api/ingest")
def ingest_list(limit: int = 20):
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT id, status, kind, url, images, role_id, error, requested_at, done_at FROM ingest ORDER BY id DESC LIMIT ?", (limit,))]
    for r in rows:
        r["images"] = json.loads(r["images"])
    con.close()
    return rows


@app.get("/api/ingest/image/{name}")
def ingest_image(name: str):
    if "/" in name or ".." in name:
        raise HTTPException(400)
    f = INGEST_DIR / name
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/api/queue/ingest")
def queue_ingest(limit: int = 3):
    """For the bot: pending items. Images are fetched by the wrapper from /api/ingest/image/{name}."""
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT id, kind, text, url, images FROM ingest WHERE status='pending' ORDER BY id LIMIT ?", (limit,))]
    for r in rows:
        r["images"] = json.loads(r["images"])
    con.close()
    return {"items": rows}


@app.put("/api/ingest/{ingest_id}")
def ingest_result(ingest_id: int, body: IngestResult):
    con = db.connect()
    it = con.execute("SELECT * FROM ingest WHERE id=?", (ingest_id,)).fetchone()
    if not it:
        con.close()
        raise HTTPException(404)
    if body.status == "failed" or not (body.title or body.description):
        with con:
            con.execute("UPDATE ingest SET status='failed', error=?, done_at=? WHERE id=?",
                        (body.error or "could not read a role from this", db.now(), ingest_id))
        con.close()
        return {"ok": True, "status": "failed"}
    fields = body.model_dump()
    fields["url"] = it["url"] or body.url
    if it["text"] and not fields.get("description"):
        fields["description"] = it["text"]
    with con:
        rid = _create_manual_role(con, fields, "screenshot" if it["kind"] == "image" else "pasted", json.loads(it["images"]))
        con.execute("UPDATE ingest SET status='ready', result=?, role_id=?, done_at=? WHERE id=?",
                    (json.dumps(fields), rid, db.now(), ingest_id))
    con.close()
    return {"ok": True, "status": "ready", "role_id": rid}


@app.get("/api/nudges")
def nudges(stale_days: int = 10):
    """Things that need a human decision: applications gone quiet, interviews to prepare for, briefs with red flags on open roles."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=stale_days)).isoformat(timespec="seconds")
    con = db.connect()
    stale = [dict(r) for r in con.execute(
        """SELECT r.id, r.title, r.company, st.changed_at, st.note FROM status st JOIN roles r ON r.id=st.role_id
           WHERE st.state='applied' AND st.changed_at <= ? ORDER BY st.changed_at""", (cutoff,))]
    for r in stale:
        r["days"] = (now - datetime.fromisoformat(r["changed_at"])).days
    progressing = [dict(r) for r in con.execute(
        """SELECT r.id, r.title, r.company, st.changed_at, st.note,
                  (SELECT status FROM research rs WHERE rs.role_id=r.id) AS brief_status,
                  (SELECT COUNT(*) FROM documents d WHERE d.role_id=r.id AND d.kind='prep' AND d.status='ready') AS prep_ready
           FROM status st JOIN roles r ON r.id=st.role_id WHERE st.state='progressing' ORDER BY st.changed_at DESC""")]
    flagged = []
    for r in con.execute(
        """SELECT r.id, r.title, r.company, rs.brief, st.state FROM research rs JOIN roles r ON r.id=rs.role_id
           LEFT JOIN status st ON st.role_id=r.id WHERE rs.status='ready' AND (st.state IS NULL OR st.state IN ('new','shortlisted','applied','progressing'))"""):
        b = json.loads(r["brief"] or "{}")
        reds = [f["text"] for f in b.get("flags", []) if f.get("kind") == "red"]
        if reds or b.get("ai_interview") == "yes":
            flagged.append({"id": r["id"], "title": r["title"], "company": r["company"], "state": r["state"] or "new",
                            "ai_interview": b.get("ai_interview"), "red": reds[:3]})
    con.close()
    return {"stale_applied": stale, "progressing": progressing, "flagged_open": flagged}


@app.get("/api/market")
def market(days: int = 60):
    """What the titles Steve searches for are actually paying, from stated (not estimated) salaries in recent roles."""
    from datetime import datetime, timedelta, timezone
    import statistics
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    con = db.connect()
    floor = get_profile()["filters"].get("salary_floor")
    rows = [dict(r) for r in con.execute(
        """SELECT r.title, r.salary_min, r.salary_max, r.salary_text, r.remote_flag, r.location, sc.track, sc.score
           FROM roles r LEFT JOIN scores sc ON sc.role_id=r.id
           WHERE r.first_seen >= ? AND r.cluster_id IS NULL AND r.salary_max IS NOT NULL AND r.salary_max >= 20000
             AND COALESCE(r.salary_text,'') != 'estimated'""", (since,))]
    con.close()

    def band(vals):
        if not vals:
            return None
        vals = sorted(vals)
        q = statistics.quantiles(vals, n=4) if len(vals) >= 4 else [vals[0], statistics.median(vals), vals[-1]]
        return {"n": len(vals), "p25": round(q[0]), "median": round(statistics.median(vals)), "p75": round(q[2]), "max": vals[-1]}

    def mid(r):
        return (r["salary_min"] + r["salary_max"]) / 2 if r["salary_min"] else r["salary_max"]

    by_track = {t: band([mid(r) for r in rows if r["track"] == t]) for t in ("engineer", "management")}
    families = {
        "Head of IT / IT Director": r"head of it|it director|director of it",
        "IT Manager / Ops Manager": r"it manager|it operations manager|service manager|technology manager",
        "Modern Workplace / EUC": r"modern workplace|euc|end user|endpoint|workplace",
        "IAM / Identity": r"identity|iam|idam|access management",
        "Infrastructure / Platform": r"infrastructure|platform|systems engineer",
        "TechOps / IT Engineer": r"techops|tech ops|it engineer|corporate it|it support engineer",
    }
    import re
    by_family = {}
    for name, rx in families.items():
        vals = [mid(r) for r in rows if re.search(rx, r["title"], re.I)]
        by_family[name] = band(vals)
    remote = band([mid(r) for r in rows if r["remote_flag"]])
    onsite = band([mid(r) for r in rows if not r["remote_flag"]])
    above = sum(1 for r in rows if floor and r["salary_max"] >= floor)
    good = band([mid(r) for r in rows if (r["score"] or 0) >= 60])
    return {"days": days, "roles_with_stated_salary": len(rows), "floor": floor, "at_or_above_floor": above,
            "by_track": by_track, "by_family": by_family, "remote": remote, "onsite": onsite, "good_fit_60_plus": good}


@app.get("/api/sources")
def sources():
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM sources ORDER BY name")]
    con.close()
    return rows


@app.post("/api/crawl")
async def crawl_now():
    return await crawl.run_all()


@app.get("/api/profile/dismissals")
def get_dismissals():
    con = db.connect()
    d = dismissal_patterns(con)
    con.close()
    return d


@app.get("/api/profile")
def get_profile():
    con = db.connect()
    p = dict(con.execute("SELECT * FROM profile WHERE id=1").fetchone())
    con.close()
    p["search_terms"] = json.loads(p["search_terms"])
    p["filters"] = json.loads(p["filters"])
    p["watchlist"] = json.loads(p.get("watchlist") or "[]")
    return p


@app.put("/api/profile")
def put_profile(body: ProfileIn):
    con = db.connect()
    cur = get_profile()
    md = body.markdown if body.markdown is not None else cur["markdown"]
    terms = body.search_terms if body.search_terms is not None else cur["search_terms"]
    filt = body.filters if body.filters is not None else cur["filters"]
    thr = body.threshold if body.threshold is not None else cur["threshold"]
    cve = body.cv_engineer if body.cv_engineer is not None else cur["cv_engineer"]
    cvm = body.cv_management if body.cv_management is not None else cur["cv_management"]
    wl = body.watchlist if body.watchlist is not None else cur["watchlist"]
    with con:
        con.execute(
            "UPDATE profile SET markdown=?, search_terms=?, filters=?, threshold=?, cv_engineer=?, cv_management=?, watchlist=?, updated_at=? WHERE id=1",
            (md, json.dumps(terms), json.dumps(filt), thr, cve, cvm, json.dumps(wl), db.now()),
        )
        # name-only entries flag roles already in the database
        from .crawl import _wn
        from .sources.watchlist import parse_entry
        names = {_wn(parse_entry(e)["name"] or parse_entry(e)["slug"]) for e in wl if e.strip()}
        for r in con.execute("SELECT id, company FROM roles WHERE watch=0"):
            if _wn(r["company"]) in names:
                con.execute("UPDATE roles SET watch=1 WHERE id=?", (r["id"],))
    con.close()
    return get_profile()


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = STATIC / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
