"""LinkedIn guest job search. Unofficial HTML endpoint, no login. Expect breakage; failures never stop the run."""
import asyncio
import html
import re

import httpx

from .base import RawRole, Source

BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

_CARD = re.compile(r'<div class="base-card[^"]*"(.*?)</div>\s*</div>\s*</li>', re.S)
_HREF = re.compile(r'href="(https://[^"]*?/jobs/view/[^"]+)"')
_TITLE = re.compile(r'class="base-search-card__title">\s*(.*?)\s*</h3>', re.S)
_COMP = re.compile(r'class="hidden-nested-link"[^>]*>\s*(.*?)\s*</a>', re.S)
_LOC = re.compile(r'class="job-search-card__location">\s*(.*?)\s*</span>', re.S)
_DATE = re.compile(r'datetime="([^"]+)"')
_ID = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')


class LinkedInSource(Source):
    name = "linkedin"
    kind = "scrape"

    async def fetch(self) -> list[RawRole]:
        if self.env.get("CAREER_LINKEDIN", "1") != "1":
            self.error = "disabled (CAREER_LINKEDIN=0)"
            return []
        base = self.env.get("CAREER_LINKEDIN_BASE", BASE)
        out: list[RawRole] = []
        try:
            async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}, follow_redirects=True) as client:
                for term in self.terms:
                    r = await client.get(base, params={
                        "keywords": term, "location": "United Kingdom", "f_TPR": "r604800", "start": 0,
                    })
                    if r.status_code == 429:
                        self.error = "rate limited (429)"
                        break
                    r.raise_for_status()
                    out.extend(self._parse(r.text))
                    await asyncio.sleep(2.0)
        except Exception as e:  # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"[:300]
        return out

    @staticmethod
    def _parse(text: str) -> list[RawRole]:
        roles = []
        for m in _CARD.finditer(text):
            card = m.group(0)
            href = _HREF.search(card)
            title = _TITLE.search(card)
            if not (href and title):
                continue
            jid = _ID.search(card)
            comp = _COMP.search(card)
            loc = _LOC.search(card)
            date = _DATE.search(card)
            location = html.unescape(loc.group(1)) if loc else ""
            roles.append(RawRole(
                external_id=jid.group(1) if jid else href.group(1),
                url=href.group(1).split("?")[0],
                title=html.unescape(re.sub(r"\s+", " ", title.group(1))),
                company=html.unescape(re.sub(r"\s+", " ", comp.group(1))) if comp else None,
                location=location,
                remote_flag="remote" in location.lower(),
                posted_at=date.group(1) if date else None,
                description=None,
            ))
        return roles
