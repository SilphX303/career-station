"""Target-company watchlist. Entries are careers URLs (Greenhouse, Lever, Ashby, Workable) or plain names.
URL entries are crawled through the ATS public job feeds; name entries only flag roles seen elsewhere."""
import asyncio
import html
import json
import re

import httpx

from .base import RawRole, Source

_ATS = [
    ("greenhouse", re.compile(r"greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"lever\.co/([A-Za-z0-9_-]+)")),
    ("ashby", re.compile(r"ashbyhq\.com/([A-Za-z0-9_.-]+)")),
    ("workable", re.compile(r"workable\.com/([A-Za-z0-9_-]+)")),
]
_TAG = re.compile(r"<[^>]+>")
_IT_WORDS = re.compile(r"\b(IT|infrastructure|platform|identity|IAM|endpoint|workplace|techops|tech ops|systems|corporate engineer|devops|SRE|security|helpdesk|service desk|support engineer|EUC|head of technology)\b", re.I)


_URL = re.compile(r"https?://\S+")


def parse_entry(line: str) -> dict:
    """'Octopus Energy https://jobs.lever.co/octoenergy', a bare URL, or a bare name."""
    line = line.strip()
    um = _URL.search(line)
    url = um.group(0) if um else ""
    label = _URL.sub("", line).strip(" -|:=") or None
    for ats, rx in _ATS:
        m = rx.search(url)
        if m:
            return {"raw": line, "ats": ats, "slug": m.group(1), "name": label or m.group(1).replace("-", " ").title()}
    return {"raw": line, "ats": None, "slug": None, "name": label or line}


def _text(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", s or ""))).strip()


class WatchlistSource(Source):
    name = "watchlist"
    kind = "api"

    def __init__(self, terms, env, entries: list[str] | None = None):
        super().__init__(terms, env)
        self.entries = [parse_entry(e) for e in (entries or []) if e.strip()]
        self._term_rx = re.compile("|".join(re.escape(t) for t in terms), re.I) if terms else None

    def _wanted(self, title: str) -> bool:
        return bool((self._term_rx and self._term_rx.search(title)) or _IT_WORDS.search(title))

    async def fetch(self) -> list[RawRole]:
        crawlable = [e for e in self.entries if e["ats"]]
        if not crawlable:
            self.error = "no careers URLs set" if not self.entries else None
            return []
        out: list[RawRole] = []
        errs = []
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "career-station/1.0"}, follow_redirects=True) as c:
            for e in crawlable:
                try:
                    fn = getattr(self, f"_{e['ats']}")
                    got = await fn(c, e["slug"])
                    for r in got:
                        r.company = e["name"]
                    out.extend([r for r in got if self._wanted(r.title)])
                except Exception as ex:  # noqa: BLE001
                    errs.append(f"{e['slug']}: {type(ex).__name__}")
                await asyncio.sleep(0.5)
        if errs:
            self.error = "; ".join(errs)[:300]
        return out

    async def _greenhouse(self, c, slug):
        r = await c.get(f"{self.env.get('CAREER_GH_BASE', 'https://boards-api.greenhouse.io')}/v1/boards/{slug}/jobs", params={"content": "true"})
        r.raise_for_status()
        roles = []
        for j in r.json().get("jobs", []):
            roles.append(RawRole(
                external_id=str(j.get("id")), url=j.get("absolute_url") or "", title=j.get("title") or "",
                company=slug.replace("-", " ").title(),
                location=(j.get("location") or {}).get("name"),
                remote_flag="remote" in ((j.get("location") or {}).get("name") or "").lower(),
                description=_text(j.get("content")), posted_at=j.get("updated_at"),
            ))
        return roles

    async def _lever(self, c, slug):
        r = await c.get(f"{self.env.get('CAREER_LEVER_BASE', 'https://api.lever.co')}/v0/postings/{slug}", params={"mode": "json"})
        r.raise_for_status()
        roles = []
        for j in r.json():
            cats = j.get("categories") or {}
            loc = cats.get("location") or ""
            roles.append(RawRole(
                external_id=j.get("id") or "", url=j.get("hostedUrl") or "", title=j.get("text") or "",
                company=slug.replace("-", " ").title(), location=loc,
                remote_flag="remote" in (loc + " " + (cats.get("commitment") or "")).lower(),
                description=_text(j.get("descriptionPlain") or j.get("description")),
                posted_at=None,
            ))
        return roles

    async def _ashby(self, c, slug):
        r = await c.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"})
        r.raise_for_status()
        roles = []
        for j in r.json().get("jobs", []):
            comp = (j.get("compensation") or {}).get("compensationTierSummary")
            roles.append(RawRole(
                external_id=j.get("id") or "", url=j.get("jobUrl") or j.get("applyUrl") or "", title=j.get("title") or "",
                company=slug.replace("-", " ").title(), location=j.get("location"),
                remote_flag=bool(j.get("isRemote")) or "remote" in (j.get("location") or "").lower(),
                salary_text=comp, description=_text(j.get("descriptionPlain") or j.get("descriptionHtml")),
                posted_at=j.get("publishedAt"),
            ))
        return roles

    async def _workable(self, c, slug):
        r = await c.get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
        r.raise_for_status()
        data = r.json()
        roles = []
        for j in data.get("jobs", []):
            roles.append(RawRole(
                external_id=j.get("shortcode") or "", url=j.get("url") or "", title=j.get("title") or "",
                company=data.get("name") or slug.title(),
                location=", ".join(x for x in (j.get("city"), j.get("country")) if x),
                remote_flag=bool(j.get("remote")) or "remote" in (j.get("workplace") or "").lower(),
                description=None,  # Workable's widget has no body; the crawl's full-text pass fetches the page
                posted_at=j.get("published_on"),
            ))
        return roles


def slug_candidates(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    base = re.sub(r"\b(ltd|limited|plc|inc|group|technologies|technology|uk)\b", "", base)
    words = base.split()
    if not words:
        return []
    joined = "".join(words)
    hyph = "-".join(words)
    first = words[0]
    out = [joined, hyph, first]
    if len(words) > 1:
        out.append(words[0] + words[1][:3])  # octoenergy-style abbreviations
    return list(dict.fromkeys(x for x in out if x))


async def resolve_feed(name: str, env: dict) -> str | None:
    """Try the public ATS feeds for a company name. Returns a careers URL or None. No scraping."""
    gh = env.get("CAREER_GH_BASE", "https://boards-api.greenhouse.io")
    lv = env.get("CAREER_LEVER_BASE", "https://api.lever.co")
    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "career-station/1.0"}, follow_redirects=True) as c:
        for slug in slug_candidates(name):
            checks = [
                (f"{gh}/v1/boards/{slug}/jobs", f"https://boards.greenhouse.io/{slug}", lambda j: bool(j.get("jobs"))),
                (f"{lv}/v0/postings/{slug}?mode=json", f"https://jobs.lever.co/{slug}", lambda j: isinstance(j, list) and len(j) > 0),
                (f"https://api.ashbyhq.com/posting-api/job-board/{slug}", f"https://jobs.ashbyhq.com/{slug}", lambda j: bool(j.get("jobs"))),
                (f"https://apply.workable.com/api/v1/widget/accounts/{slug}", f"https://apply.workable.com/{slug}", lambda j: bool(j.get("jobs"))),
            ]
            for api, public, ok in checks:
                try:
                    r = await c.get(api)
                    if r.status_code == 200 and ok(r.json()):
                        return public
                except Exception:  # noqa: BLE001
                    continue
    return None
