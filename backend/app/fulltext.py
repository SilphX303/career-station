"""Fetch the full text of a job ad. Reed has a details API; everything else is a best-effort HTML extraction."""
import html
import re

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
_SCRIPT = re.compile(r"<(script|style|noscript|svg|nav|header|footer|aside|form)\b.*?</\1>", re.S | re.I)
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
    if d[-1] not in ".!?)]\"'":
        return "partial", "ends mid-sentence"
    if not _SPEC_WORDS.search(d):
        return "partial", "no job or person spec wording"
    return "ok", None


def looks_truncated(desc: str | None) -> bool:
    return assess(desc)[0] == "partial"


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
        return best[:12000]
    for m in _BLOCK.finditer(page):
        t = _to_text(m.group(2))
        if len(t) > len(best):
            best = t
    if len(best) < 400:
        best = _to_text(page)
    return best[:12000]


async def reed_full(client: httpx.AsyncClient, base: str, job_id: str) -> str | None:
    r = await client.get(f"{base}/jobs/{job_id}")
    if r.status_code != 200:
        return None
    return (r.json() or {}).get("jobDescription")


async def fetch_url(url: str) -> str | None:
    if not url:
        return None
    async with httpx.AsyncClient(timeout=25, headers={"User-Agent": UA}, follow_redirects=True) as client:
        r = await client.get(url)
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            return None
        return extract(r.text)


def clean_reed(desc: str | None) -> str | None:
    """Reed details come back as HTML."""
    return _to_text(desc) if desc else None
