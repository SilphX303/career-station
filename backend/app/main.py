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

from . import crawl, db

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
                  r.url, r.posted_at, r.first_seen, s.name AS source,
                  sc.score, sc.reasons, st.state
           FROM roles r
           JOIN sources s ON s.id = r.source_id
           LEFT JOIN scores sc ON sc.role_id = r.id
           LEFT JOIN status st ON st.role_id = r.id
           WHERE 1=1"""
    args: list = []
    if state:
        q += " AND st.state = ?"
        args.append(state)
    else:
        q += " AND (st.state IS NULL OR st.state NOT IN ('dismissed','rejected','declined'))"
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
        """SELECT r.*, s.name AS source, sc.score, sc.reasons, sc.gaps, st.state, st.note
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
