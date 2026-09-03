"""Collapse the same role posted by several agencies into one cluster."""
import re
from difflib import SequenceMatcher

from . import db

_AGENCY = re.compile(r"recruit|resourc|placement|staffing|talent|search|people|consultancy|personnel|appointments|selection|associates|partners", re.I)
_WORD = re.compile(r"[a-z0-9]+")


def _shingles(text: str, n: int = 5) -> set:
    w = _WORD.findall((text or "").lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _title_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def is_agency(company: str | None) -> bool:
    return bool(company and _AGENCY.search(company))


def run(con, days: int = 14, desc_threshold: float = 0.45, title_threshold: float = 0.6) -> dict:
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = [dict(r) for r in con.execute(
        "SELECT id, title, company, description, first_seen, cluster_id FROM roles WHERE first_seen >= ? AND filtered = 0 AND length(COALESCE(description,'')) > 300 ORDER BY first_seen",
        (since,))]
    sh = {r["id"]: _shingles(r["description"]) for r in rows}
    # union-find over similar pairs
    parent = {r["id"]: r["id"] for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs = 0
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if _title_sim(a["title"], b["title"]) < title_threshold:
                continue
            if _jaccard(sh[a["id"]], sh[b["id"]]) >= desc_threshold:
                parent[find(a["id"])] = find(b["id"])
                pairs += 1
    groups: dict[int, list[dict]] = {}
    for r in rows:
        groups.setdefault(find(r["id"]), []).append(r)
    changed = 0
    with con:
        for members in groups.values():
            if len(members) < 2:
                # singleton: make sure it is not stuck as a member of an old cluster
                if members[0]["cluster_id"] is not None:
                    con.execute("UPDATE roles SET cluster_id=NULL WHERE id=?", (members[0]["id"],))
                continue
            direct = [m for m in members if not is_agency(m["company"])]
            head = (direct or members)[0]  # earliest direct employer, else earliest
            for m in members:
                want = None if m["id"] == head["id"] else head["id"]
                if m["cluster_id"] != want:
                    con.execute("UPDATE roles SET cluster_id=? WHERE id=?", (want, m["id"]))
                    changed += 1
    return {"compared": len(rows), "pairs": pairs, "clusters": sum(1 for g in groups.values() if len(g) > 1), "changed": changed}
