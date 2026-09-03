"""Match inbox findings (company, title, state) to stored roles. Fuzzy on company, then title."""
import re
from difflib import SequenceMatcher

_STOP = re.compile(r"\b(ltd|limited|plc|uk|the|group|technologies|technology|recruitment|inc)\b")


def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
    return re.sub(r"\s+", " ", _STOP.sub("", s)).strip()


def _sim(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def best_match(company: str, title: str | None, roles: list[dict]) -> tuple[dict | None, float]:
    """roles: [{id, company, title}]. Returns (role, confidence)."""
    best, score = None, 0.0
    for r in roles:
        c = _sim(company, r.get("company") or "")
        if c < 0.6:
            continue
        t = _sim(title, r.get("title") or "") if title else 0.5
        s = 0.65 * c + 0.35 * t
        if s > score:
            best, score = r, s
    return (best, score) if score >= 0.6 else (None, score)
