"""Run every enabled source, upsert roles, record source health."""
import json
import logging
import os

from . import db
from .sources import REGISTRY

log = logging.getLogger("career.crawl")


async def run_all() -> dict:
    con = db.connect()
    prof = con.execute("SELECT search_terms FROM profile WHERE id=1").fetchone()
    terms = json.loads(prof["search_terms"]) if prof else []
    env = dict(os.environ)
    summary = {}
    for name, cls in REGISTRY.items():
        con.execute("INSERT OR IGNORE INTO sources (name, kind) VALUES (?, ?)", (name, cls.kind))
        row = con.execute("SELECT id, enabled FROM sources WHERE name=?", (name,)).fetchone()
        if not row["enabled"]:
            continue
        src = cls(terms, env)
        roles = await src.fetch()
        new = 0
        ts = db.now()
        with con:
            for r in roles:
                h = r.dedupe_hash()
                exists = con.execute("SELECT id FROM roles WHERE hash=?", (h,)).fetchone()
                if exists:
                    con.execute("UPDATE roles SET last_seen=? WHERE id=?", (ts, exists["id"]))
                    continue
                cur = con.execute(
                    """INSERT INTO roles (source_id, external_id, url, title, company, location, remote_flag,
                       salary_min, salary_max, salary_text, description, posted_at, first_seen, last_seen, hash)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (row["id"], r.external_id, r.url, r.title, r.company, r.location, int(r.remote_flag),
                     r.salary_min, r.salary_max, r.salary_text, r.description, r.posted_at, ts, ts, h),
                )
                con.execute("INSERT OR IGNORE INTO status (role_id, state, changed_at) VALUES (?, 'new', ?)", (cur.lastrowid, ts))
                new += 1
            con.execute(
                "UPDATE sources SET last_run=?, last_ok=?, last_error=? WHERE id=?",
                (ts, 0 if src.error else 1, src.error, row["id"]),
            )
        summary[name] = {"fetched": len(roles), "new": new, "error": src.error}
        log.info("%s: fetched=%d new=%d error=%s", name, len(roles), new, src.error)
    con.close()
    return summary
