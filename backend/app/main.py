import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import crawl, db, notify, sync

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


class StatusIn(BaseModel):
    state: str
    note: str | None = None


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


class ProfileIn(BaseModel):
    markdown: str | None = None
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
                  r.url, r.posted_at, r.first_seen, r.filtered, r.filter_reason, s.name AS source,
                  sc.score, sc.reasons, sc.track, st.state
           FROM roles r
           JOIN sources s ON s.id = r.source_id
           LEFT JOIN scores sc ON sc.role_id = r.id
           LEFT JOIN status st ON st.role_id = r.id
           WHERE 1=1"""
    args: list = []
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
    return d


@app.put("/api/roles/{role_id}/status")
def set_status(role_id: int, body: StatusIn):
    if body.state not in STATES:
        raise HTTPException(400, f"state must be one of {sorted(STATES)}")
    con = db.connect()
    if not con.execute("SELECT 1 FROM roles WHERE id=?", (role_id,)).fetchone():
        con.close()
        raise HTTPException(404)
    with con:
        con.execute(
            """INSERT INTO status (role_id, state, changed_at, note) VALUES (?,?,?,?)
               ON CONFLICT(role_id) DO UPDATE SET state=excluded.state, changed_at=excluded.changed_at, note=excluded.note""",
            (role_id, body.state, db.now(), body.note),
        )
    con.close()
    return {"ok": True, "state": body.state}


@app.get("/api/queue/unscored")
def queue_unscored(limit: int = 40):
    """For the scoring bot: roles that passed filters and have no score yet. Includes the profile."""
    con = db.connect()
    prof = get_profile()
    rows = [dict(r) for r in con.execute(
        """SELECT r.id, r.title, r.company, r.location, r.remote_flag, r.salary_min, r.salary_max, r.salary_text,
                  r.url, r.description, r.posted_at
           FROM roles r LEFT JOIN scores sc ON sc.role_id = r.id LEFT JOIN status st ON st.role_id = r.id
           WHERE r.filtered = 0 AND sc.role_id IS NULL
             AND (st.state IS NULL OR st.state NOT IN ('dismissed','rejected','declined'))
           ORDER BY r.first_seen DESC LIMIT ?""", (limit,))]
    con.close()
    return {"profile": prof["markdown"], "threshold": prof["threshold"], "roles": rows}


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
    with con:
        con.execute(
            """INSERT INTO scores (role_id, score, reasons, gaps, scored_at, model, track) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(role_id) DO UPDATE SET score=excluded.score, reasons=excluded.reasons,
               gaps=excluded.gaps, scored_at=excluded.scored_at, model=excluded.model, track=excluded.track""",
            (role_id, body.score, json.dumps(body.reasons), json.dumps(body.gaps), db.now(), body.model, body.track),
        )
    notified = False
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
    ok, failed, notified = [], [], 0
    for item in body.scores:
        try:
            r = await put_score(item.role_id, ScoreIn(**item.model_dump(exclude={"role_id"})))
            ok.append(item.role_id)
            notified += int(bool(r.get("notified")))
        except HTTPException as e:
            failed.append({"role_id": item.role_id, "why": e.detail})
    return {"scored": len(ok), "failed": failed, "notified": notified}


@app.post("/api/sync/status")
def sync_status(body: SyncIn):
    """Inbox sweep posts what it found. Fuzzy-matches to roles and updates status. Never downgrades progressing to applied."""
    order = {"new": 0, "shortlisted": 1, "applied": 2, "progressing": 3, "rejected": 4, "declined": 4, "dismissed": 4}
    con = db.connect()
    roles = [dict(r) for r in con.execute(
        "SELECT r.id, r.company, r.title, st.state FROM roles r LEFT JOIN status st ON st.role_id=r.id")]
    matched, unmatched = [], []
    ts = db.now()
    with con:
        for it in body.items:
            if it.state not in STATES:
                unmatched.append({**it.model_dump(), "why": "bad state"})
                continue
            role, conf = sync.best_match(it.company, it.title, roles)
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
    return {"matched": matched, "unmatched": unmatched}


@app.get("/api/sources")
def sources():
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM sources ORDER BY name")]
    con.close()
    return rows


@app.post("/api/crawl")
async def crawl_now():
    return await crawl.run_all()


@app.get("/api/profile")
def get_profile():
    con = db.connect()
    p = dict(con.execute("SELECT * FROM profile WHERE id=1").fetchone())
    con.close()
    p["search_terms"] = json.loads(p["search_terms"])
    p["filters"] = json.loads(p["filters"])
    return p


@app.put("/api/profile")
def put_profile(body: ProfileIn):
    con = db.connect()
    cur = get_profile()
    md = body.markdown if body.markdown is not None else cur["markdown"]
    terms = body.search_terms if body.search_terms is not None else cur["search_terms"]
    filt = body.filters if body.filters is not None else cur["filters"]
    thr = body.threshold if body.threshold is not None else cur["threshold"]
    with con:
        con.execute(
            "UPDATE profile SET markdown=?, search_terms=?, filters=?, threshold=?, updated_at=? WHERE id=1",
            (md, json.dumps(terms), json.dumps(filt), thr, db.now()),
        )
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
