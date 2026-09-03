"""Hard filters applied at crawl time. A filtered role is stored but hidden and never queued for scoring."""
import re


def apply(role: dict, filters: dict) -> tuple[bool, str | None]:
    """Return (filtered, reason)."""
    text = " ".join(str(role.get(k) or "") for k in ("title", "description")).lower()
    title = (role.get("title") or "").lower()
    loc = (role.get("location") or "").lower()
    remote = bool(role.get("remote_flag"))

    for term in filters.get("exclude_terms", []):
        t = term.lower()
        if t in title or (len(t) > 8 and t in text):
            return True, f"excluded term: {term}"

    floor = filters.get("salary_floor")
    smax = role.get("salary_max") or role.get("salary_min")
    if floor and smax and smax < floor * 0.9:
        return True, f"salary £{smax:,} below floor"

    locs = [l.lower() for l in filters.get("locations", [])]
    if locs and not remote and loc:
        if not any(l in loc for l in locs) and not re.search(r"\b(uk|united kingdom|hybrid|remote)\b", loc):
            return True, f"location: {role.get('location')}"

    return False, None
