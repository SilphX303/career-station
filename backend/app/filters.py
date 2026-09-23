"""Hard filters applied at crawl time. A filtered role is stored but hidden and never queued for scoring.

Salary has three outcomes rather than two:
  - at or above 90% of the floor: passes
  - between the near-miss band and 90% of the floor: hidden, but flagged near_miss so it sits in a
    reviewable list instead of vanishing (board salary data is often wrong or a guess)
  - below the near-miss band: hidden outright
A role restored by hand (or by a salary found in the fetched ad) gets filter_override=1 and is never
re-filtered, whatever a later crawl or paste says about it.
"""
import re

from . import fulltext

HARD_FRACTION = 0.9          # existing rule: max below 90% of the floor fails the salary filter
DEFAULT_NEAR_MISS_PCT = 80   # of the floor; roles paying at least this much go to Near miss, not the bin


def near_miss_fraction(filters: dict) -> float:
    try:
        pct = float(filters.get("near_miss_pct", DEFAULT_NEAR_MISS_PCT))
    except (TypeError, ValueError):
        pct = DEFAULT_NEAR_MISS_PCT
    return max(0.0, min(pct, HARD_FRACTION * 100)) / 100


def apply(role: dict, filters: dict) -> tuple[bool, str | None, bool]:
    """Return (filtered, reason, near_miss). Salary is checked last so near_miss only marks roles
    that would have passed on everything else."""
    text = " ".join(str(role.get(k) or "") for k in ("title", "description")).lower()
    title = (role.get("title") or "").lower()
    loc = (role.get("location") or "").lower()
    remote = bool(role.get("remote_flag"))

    for term in filters.get("exclude_terms", []):
        t = term.lower()
        if t in title or (len(t) > 8 and t in text):
            return True, f"excluded term: {term}", False

    locs = [l.lower() for l in filters.get("locations", [])]
    if locs and not remote and loc:
        if not any(l in loc for l in locs) and not re.search(r"\b(uk|united kingdom|hybrid|remote)\b", loc):
            return True, f"location: {role.get('location')}", False

    floor = filters.get("salary_floor")
    smax = role.get("salary_max") or role.get("salary_min")
    if floor and smax and smax < floor * HARD_FRACTION:
        if smax >= floor * near_miss_fraction(filters):
            return True, f"salary £{smax:,} near floor", True
        return True, f"salary £{smax:,} below floor", False

    return False, None, False


def salary_from_ad(role: dict, text: str | None) -> tuple[int, int] | None:
    """A salary stated in the ad text beats the board's figure, but only upwards or where the board had
    nothing better than a guess. Never used to lower a stated figure, so it can only ever unhide."""
    found = fulltext.parse_salary(text)
    if not found:
        return None
    lo, hi = found
    cur_max = role.get("salary_max") or role.get("salary_min")
    weak = not cur_max or (role.get("salary_text") or "") == "estimated"
    if weak or hi > cur_max:
        return lo, hi
    return None


def reapply_hidden(con, filters: dict) -> dict:
    """Re-check every hidden role that was not restored by hand: re-read a salary from the stored ad,
    re-run the filters, and unhide or reclassify. Never touches visible roles or overrides."""
    from . import db
    rows = [dict(r) for r in con.execute(
        """SELECT id, title, description, location, remote_flag, salary_min, salary_max, salary_text
           FROM roles WHERE filtered = 1 AND filter_override = 0""")]
    out = {"checked": len(rows), "unhidden": 0, "near_miss": 0, "still_hidden": 0, "salary_from_ad": 0}
    ts = db.now()
    with con:
        for role in rows:
            sal = salary_from_ad(role, role.get("description"))
            if sal:
                role["salary_min"], role["salary_max"], role["salary_text"] = sal[0], sal[1], "from ad"
                con.execute("UPDATE roles SET salary_min=?, salary_max=?, salary_text=? WHERE id=?",
                            (sal[0], sal[1], "from ad", role["id"]))
                out["salary_from_ad"] += 1
            fl, why, nm = apply(role, filters)
            if not fl:
                con.execute(
                    """UPDATE roles SET filtered=0, filter_reason=NULL, near_miss=0,
                       filter_override=?, override_note=? WHERE id=?""",
                    (int(bool(sal)), f"salary £{sal[0]:,} to £{sal[1]:,} read from the ad" if sal else None, role["id"]))
                con.execute("INSERT OR IGNORE INTO status (role_id, state, changed_at) VALUES (?, 'new', ?)", (role["id"], ts))
                out["unhidden"] += 1
            else:
                con.execute("UPDATE roles SET filter_reason=?, near_miss=? WHERE id=?", (why, int(nm), role["id"]))
                out["near_miss" if nm else "still_hidden"] += 1
    return out
