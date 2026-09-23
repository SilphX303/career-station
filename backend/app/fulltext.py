"""Fetch the full text of a job ad. Reed has a details API; everything else is a best-effort HTML extraction."""
import html
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
_SCRIPT = re.compile(r"<(script|style|noscript|svg|nav|header|footer|aside|form)\b.*?</\1>", re.S | re.I)
_CODE = re.compile(r"<(script|style|noscript|svg)\b.*?</\1>", re.S | re.I)  # for the salary scan: keep headers, where boards put the range
_MAIN = re.compile(r"<(article|main)\b[^>]*>(.*?)</\1>", re.S | re.I)
_BLOCK = re.compile(r"<(section|div)\b[^>]*>(.*?)</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<\s*(br|/p|/li|/h[1-6]|/div|/tr)\s*/?>", re.I)


_SPEC_WORDS = re.compile(r"responsib|requirement|experience|skills|you will|you'll|about the role|about you|what you|we are looking|the role|duties|qualifications", re.I)


def assess(desc: str | None) -> tuple[str, str | None]:
    """Return (quality, reason). quality is 'ok' or 'partial'."""
    if not desc or not desc.strip():
        return "partial", "no description"
    d = desc.strip()
    if d.endswith("...") or d.endswith("…"):
        return "partial", "ends with an ellipsis"
    if len(d) < 600:
        return "partial", f"only {len(d)} characters"
    if len(d) < 1500 and d[-1] not in ".!?)]\"'":
        return "partial", "ends mid-sentence"
    if not _SPEC_WORDS.search(d):
        return "partial", "no job or person spec wording"
    return "ok", None


def looks_truncated(desc: str | None) -> bool:
    return assess(desc)[0] == "partial"


_CUT_MARKERS = re.compile(
    r"\n\s*(Apply for this job|Apply now|Apply for job|Create alert|Create a job alert|Similar jobs|Related jobs|Report this job|Share this job|Save this job|Get new jobs for this search by email|By creating an alert)\b.*",
    re.S | re.I,
)


def trim_chrome(text: str) -> str:
    """Drop page furniture that follows the ad body, then trailing short nav-like lines."""
    t = _CUT_MARKERS.sub("", text)
    lines = t.rstrip().split("\n")
    while lines and len(lines[-1].strip()) < 40 and len(lines) > 5 and not lines[-1].strip().endswith((".", "!", "?")):
        lines.pop()
    return "\n".join(lines).strip()


def _to_text(fragment: str) -> str:
    t = _BR.sub("\n", fragment)
    t = _TAG.sub(" ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def extract(page: str) -> str:
    """Pick the largest content block on the page. Crude, but ads are usually one big div."""
    page = _SCRIPT.sub(" ", page)
    best = ""
    for m in _MAIN.finditer(page):
        t = _to_text(m.group(2))
        if len(t) > len(best):
            best = t
    if len(best) >= 400:
        return trim_chrome(best)[:12000]
    for m in _BLOCK.finditer(page):
        t = _to_text(m.group(2))
        if len(t) > len(best):
            best = t
    if len(best) < 400:
        best = _to_text(page)
    return trim_chrome(best)[:12000]


async def reed_full(client: httpx.AsyncClient, base: str, job_id: str) -> str | None:
    r = await client.get(f"{base}/jobs/{job_id}")
    if r.status_code != 200:
        return None
    return (r.json() or {}).get("jobDescription")


async def fetch_page(url: str) -> tuple[str | None, str | None]:
    """(ad body, whole page as text). The body is what gets stored; the whole page is only scanned for a
    salary, because boards often put the range in a header block outside the ad body."""
    if not url:
        return None, None
    async with httpx.AsyncClient(timeout=25, headers={"User-Agent": UA}, follow_redirects=True) as client:
        r = await client.get(url)
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            return None, None
        return extract(r.text), _to_text(_CODE.sub(" ", r.text))[:60000]


async def fetch_url(url: str) -> str | None:
    return (await fetch_page(url))[0]


# --- salary in ad text -------------------------------------------------------------------------
# Accepts "£65,000 – £90,000", "£65k-£90k", "£65-90k", "£65,000 to 90,000", "GBP 70,000", "up to £80k",
# "£75,000 per annum". Ignores day and hourly rates, and anything outside 15k to 300k (bonuses, budgets).
_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?(k)?"
_CUR = r"(?:£|GBP\s?)"
_RANGE = re.compile(rf"({_CUR})?\s?{_NUM}\s?(?:-|–|—|to|and)\s?({_CUR})?\s?{_NUM}", re.I)
_SINGLE = re.compile(rf"{_CUR}\s?{_NUM}", re.I)
_UNIT = re.compile(r"(per\s+day|/\s*day|a\s+day|daily|day\s+rate|per\s+hour|/\s*h(?:ou)?r\b|p/h|hourly|per\s+month|/\s*month|pcm|per\s+week|/\s*week|weekly)", re.I)
_ANNUAL = re.compile(r"(per\s+annum|p\.?a\.?\b|per\s+year|a\s+year|/\s*year|annual)", re.I)
_LOW, _HIGH = 15_000, 300_000


def _amount(num: str, k: str | None, sibling_k: bool = False) -> int | None:
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    if k or (sibling_k and v < 1000):
        v *= 1000
    v = int(round(v))
    return v if _LOW <= v <= _HIGH else None


def _is_rate(text: str, end: int) -> bool:
    """True when the figure is followed (before any punctuation) by a day/hour/month unit, unless an
    annual marker comes first."""
    window = re.split(r"[\n,;.(]", text[end:end + 40], 1)[0]
    u, a = _UNIT.search(window), _ANNUAL.search(window)
    return bool(u) and (not a or u.start() < a.start())


def parse_salary(text: str | None) -> tuple[int, int] | None:
    """Return (min, max) in GBP from a stated annual salary, or None. Ranges beat single figures;
    the first valid range wins, else the largest valid single figure."""
    if not text:
        return None
    t = text[:60000]
    for m in _RANGE.finditer(t):
        cur1, n1, k1, cur2, n2, k2 = m.groups()
        if not (cur1 or cur2):
            continue
        if _is_rate(t, m.end()):
            continue
        a = _amount(n1, k1, sibling_k=bool(k2))
        b = _amount(n2, k2, sibling_k=bool(k1))
        if a and b:
            return (a, b) if a <= b else (b, a)
    best = None
    for m in _SINGLE.finditer(t):
        n, k = m.groups()
        if _is_rate(t, m.end()):
            continue
        v = _amount(n, k)
        if v and (best is None or v > best):
            best = v
    return (best, best) if best else None


def clean_reed(desc: str | None) -> str | None:
    """Reed details come back as HTML."""
    return _to_text(desc) if desc else None
