"""Run every enabled source, upsert roles, record source health."""
import asyncio
import json
import logging
import os

import httpx

from . import db
from . import cluster, filters, fulltext
from .sources import REGISTRY
from .sources.watchlist import parse_entry

log = logging.getLogger("career.crawl")


async def run_all() -> dict:
    con = db.connect()
    prof = con.execute("SELECT search_terms, filters, watchlist FROM profile WHERE id=1").fetchone()
    terms = json.loads(prof["search_terms"]) if prof else []
    filt = json.loads(prof["filters"]) if prof else {}
    watch_entries = json.loads(prof["watchlist"]) if prof else []
    watch_names = {(_wn(parse_entry(e)["name"] or parse_entry(e)["slug"])) for e in watch_entries if e.strip()}
    env = dict(os.environ)
    summary = {}
    to_fill: list[tuple[int, str, str | None, str]] = []
    for name, cls in REGISTRY.items():
        con.execute("INSERT OR IGNORE INTO sources (name, kind) VALUES (?, ?)", (name, cls.kind))
        row = con.execute("SELECT id, enabled FROM sources WHERE name=?", (name,)).fetchone()
        if not row["enabled"]:
            continue
        src = cls(terms, env, watch_entries) if name == "watchlist" else cls(terms, env)
        roles = await src.fetch()
        new = 0
        ts = db.now()
        with con:
            for r in roles:
                h = r.dedupe_hash()
                exists = con.execute("SELECT id FROM roles WHERE hash=?", (h,)).fetchone()
                if exists:
                    # Same role seen on another board: keep the record, but fill in anything the first sighting lacked
                    con.execute(
                        """UPDATE roles SET last_seen=?,
                           description=COALESCE(NULLIF(description,''), ?),
                           salary_min=COALESCE(salary_min, ?), salary_max=COALESCE(salary_max, ?),
                           watch=MAX(watch, ?)
                           WHERE id=?""",
                        (ts, r.description, r.salary_min, r.salary_max, int(name == "watchlist" or _wn(r.company) in watch_names), exists["id"]))
                    continue
                fl, why = filters.apply(r.__dict__, filt)
                dq, dr = fulltext.assess(r.description)
                watch = int(name == "watchlist" or _wn(r.company) in watch_names)
                cur = con.execute(
                    """INSERT INTO roles (source_id, external_id, url, title, company, location, remote_flag,
                       salary_min, salary_max, salary_text, description, posted_at, first_seen, last_seen, hash,
                       filtered, filter_reason, desc_quality, desc_reason, watch)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (row["id"], r.external_id, r.url, r.title, r.company, r.location, int(r.remote_flag),
                     r.salary_min, r.salary_max, r.salary_text, r.description, r.posted_at, ts, ts, h, int(fl), why, dq, dr, watch),
                )
                con.execute("INSERT OR IGNORE INTO status (role_id, state, changed_at) VALUES (?, 'new', ?)", (cur.lastrowid, ts))
                new += 1
                if not fl and dq == "partial":
                    to_fill.append((cur.lastrowid, name, r.external_id, r.url))
            not_set = bool(src.error) and ("not set" in src.error or "disabled" in src.error)
            con.execute(
                "UPDATE sources SET last_run=?, last_ok=?, last_error=? WHERE id=?",
                (ts, None if not_set else (0 if src.error else 1), "not set up" if not_set else src.error, row["id"]),
            )
        summary[name] = {"fetched": len(roles), "new": new, "error": src.error}
        log.info("%s: fetched=%d new=%d error=%s", name, len(roles), new, src.error)
    filled = await fill_descriptions(con, to_fill, env)
    summary["fulltext"] = filled
    try:
        summary["clusters"] = cluster.run(con)
    except Exception as e:  # noqa: BLE001
        log.warning("cluster pass failed: %s", e)
    con.close()
    return summary


async def fill_descriptions(con, items, env, cap: int = 60) -> dict:
    """Replace stub descriptions with the full ad before scoring. Best effort; never raises."""
    ok = skipped = failed = 0
    reed_base = env.get("CAREER_REED_BASE", "https://www.reed.co.uk/api/1.0")
    reed_key = env.get("CAREER_REED_KEY")
    async with httpx.AsyncClient(auth=(reed_key, "") if reed_key else None, timeout=25) as reed_client:
        for rid, source, ext, url in items[:cap]:
            try:
                if source == "reed" and ext and reed_key:
                    text = fulltext.clean_reed(await fulltext.reed_full(reed_client, reed_base, ext))
                else:
                    text = await fulltext.fetch_url(url)
                if text and len(text) > 300:
                    dq, dr = fulltext.assess(text)
                    with con:
                        con.execute("UPDATE roles SET description=?, desc_quality=?, desc_reason=? WHERE id=?", (text, dq, dr, rid))
                    ok += 1
                else:
                    skipped += 1
                await asyncio.sleep(0.4)
            except Exception as e:  # noqa: BLE001
                failed += 1
                log.info("fulltext %s %s: %s", source, rid, e)
    return {"filled": ok, "skipped": skipped, "failed": failed, "queued": len(items)}


def _wn(name: str | None) -> str:
    import re
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    s = re.sub(r"\b(ltd|limited|plc|uk|the|inc|group)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()
