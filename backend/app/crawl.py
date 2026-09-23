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
    near_fill: list[tuple[int, str, str | None, str]] = []
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
                # A salary written in the ad beats the board's figure (upwards only; see filters.salary_from_ad)
                sal = filters.salary_from_ad(r.__dict__, r.description)
                if sal:
                    r.salary_min, r.salary_max, r.salary_text = sal[0], sal[1], "from ad"
                fl, why, nm = filters.apply(r.__dict__, filt)
                dq, dr = fulltext.assess(r.description)
                watch = int(name == "watchlist" or _wn(r.company) in watch_names)
                cur = con.execute(
                    """INSERT INTO roles (source_id, external_id, url, title, company, location, remote_flag,
                       salary_min, salary_max, salary_text, description, posted_at, first_seen, last_seen, hash,
                       filtered, filter_reason, desc_quality, desc_reason, watch, near_miss)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (row["id"], r.external_id, r.url, r.title, r.company, r.location, int(r.remote_flag),
                     r.salary_min, r.salary_max, r.salary_text, r.description, r.posted_at, ts, ts, h, int(fl), why, dq, dr, watch, int(nm)),
                )
                con.execute("INSERT OR IGNORE INTO status (role_id, state, changed_at) VALUES (?, 'new', ?)", (cur.lastrowid, ts))
                new += 1
                if dq == "partial":
                    # visible roles first; near misses after, since a fetched ad may carry the salary that rescues them
                    if not fl:
                        to_fill.append((cur.lastrowid, name, r.external_id, r.url))
                    elif nm:
                        near_fill.append((cur.lastrowid, name, r.external_id, r.url))
            not_set = bool(src.error) and ("not set" in src.error or "disabled" in src.error)
            con.execute(
                "UPDATE sources SET last_run=?, last_ok=?, last_error=? WHERE id=?",
                (ts, None if not_set else (0 if src.error else 1), "not set up" if not_set else src.error, row["id"]),
            )
        summary[name] = {"fetched": len(roles), "new": new, "error": src.error}
        log.info("%s: fetched=%d new=%d error=%s", name, len(roles), new, src.error)
    filled = await fill_descriptions(con, to_fill + near_fill, env, filt=filt)
    summary["fulltext"] = filled
    try:
        summary["clusters"] = cluster.run(con)
    except Exception as e:  # noqa: BLE001
        log.warning("cluster pass failed: %s", e)
    con.close()
    return summary


async def fill_descriptions(con, items, env, cap: int = 60, filt: dict | None = None) -> dict:
    """Replace stub descriptions with the full ad before scoring. Best effort; never raises.
    Also reads the salary off the fetched page: a near miss whose ad states a range that clears the floor is unhidden."""
    ok = skipped = failed = rescued = 0
    if filt is None:
        prof = con.execute("SELECT filters FROM profile WHERE id=1").fetchone()
        filt = json.loads(prof["filters"]) if prof else {}
    reed_base = env.get("CAREER_REED_BASE", "https://www.reed.co.uk/api/1.0")
    reed_key = env.get("CAREER_REED_KEY")
    async with httpx.AsyncClient(auth=(reed_key, "") if reed_key else None, timeout=25) as reed_client:
        for rid, source, ext, url in items[:cap]:
            try:
                page = None
                if source == "reed" and ext and reed_key:
                    text = fulltext.clean_reed(await fulltext.reed_full(reed_client, reed_base, ext))
                else:
                    text, page = await fulltext.fetch_page(url)
                if text and len(text) > 300:
                    dq, dr = fulltext.assess(text)
                    with con:
                        con.execute("UPDATE roles SET description=?, desc_quality=?, desc_reason=? WHERE id=?", (text, dq, dr, rid))
                    ok += 1
                else:
                    skipped += 1
                rescued += int(_salary_from_page(con, rid, page or text, filt))
                await asyncio.sleep(0.4)
            except Exception as e:  # noqa: BLE001
                failed += 1
                log.info("fulltext %s %s: %s", source, rid, e)
    return {"filled": ok, "skipped": skipped, "failed": failed, "queued": len(items), "unhidden_by_salary": rescued}


def _salary_from_page(con, rid: int, text: str | None, filt: dict) -> bool:
    """Apply a salary found in the fetched ad. Returns True when that unhid the role."""
    role = con.execute(
        """SELECT id, title, description, location, remote_flag, salary_min, salary_max, salary_text,
           filtered, near_miss, filter_override FROM roles WHERE id=?""", (rid,)).fetchone()
    if not role:
        return False
    role = dict(role)
    sal = filters.salary_from_ad(role, text)
    if not sal:
        return False
    with con:
        con.execute("UPDATE roles SET salary_min=?, salary_max=?, salary_text='from ad' WHERE id=?", (sal[0], sal[1], rid))
    if not role["filtered"] or role["filter_override"]:
        return False
    role.update(salary_min=sal[0], salary_max=sal[1], salary_text="from ad")
    fl, why, nm = filters.apply(role, filt)
    with con:
        if fl:
            con.execute("UPDATE roles SET filter_reason=?, near_miss=? WHERE id=?", (why, int(nm), rid))
            return False
        con.execute(
            """UPDATE roles SET filtered=0, filter_reason=NULL, near_miss=0, filter_override=1, override_note=? WHERE id=?""",
            (f"salary £{sal[0]:,} to £{sal[1]:,} read from the ad", rid))
        con.execute("INSERT OR IGNORE INTO status (role_id, state, changed_at) VALUES (?, 'new', ?)", (rid, db.now()))
    log.info("role %s unhidden: ad states £%s to £%s", rid, sal[0], sal[1])
    return True


def _wn(name: str | None) -> str:
    import re
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    s = re.sub(r"\b(ltd|limited|plc|uk|the|inc|group)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()
