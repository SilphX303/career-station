"""Generic RSS/Atom job feeds. CAREER_RSS_FEEDS is a comma-separated list of feed URLs.
Many boards expose search-result feeds, e.g. CWJobs and Technojobs; paste the URL of a saved search."""
import html
import re
import xml.etree.ElementTree as ET

import httpx

from .base import RawRole, Source

_TAG = re.compile(r"<[^>]+>")
_SAL = re.compile(r"£\s?(\d{2,3})[,.]?(\d{3})?\s?(k)?", re.I)


class RssSource(Source):
    name = "rss"
    kind = "rss"

    async def fetch(self) -> list[RawRole]:
        feeds = [u.strip() for u in self.env.get("CAREER_RSS_FEEDS", "").split(",") if u.strip()]
        if not feeds:
            self.error = "CAREER_RSS_FEEDS not set"
            return []
        out: list[RawRole] = []
        errs = []
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "career-station/1.0"}) as client:
            for url in feeds:
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    out.extend(self._parse(r.text, url))
                except Exception as e:  # noqa: BLE001
                    errs.append(f"{url[:40]}: {type(e).__name__}")
        if errs:
            self.error = "; ".join(errs)[:300]
        return out

    def _parse(self, text: str, feed_url: str) -> list[RawRole]:
        root = ET.fromstring(_xml_safe(text).encode())
        ns = {"a": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//a:entry", ns)
        roles = []
        for it in items:
            title = _t(it, "title", ns)
            link = _t(it, "link", ns) or (it.find("a:link", ns).get("href") if it.find("a:link", ns) is not None else "")
            desc = html.unescape(_TAG.sub(" ", _t(it, "description", ns) or _t(it, "a:summary", ns) or _t(it, "a:content", ns)))
            desc = re.sub(r"\s+", " ", desc).strip()
            date = _t(it, "pubDate", ns) or _t(it, "a:updated", ns)
            company, location = self._guess(title, desc)
            smin, smax = self._salary(desc)
            roles.append(RawRole(
                external_id=_t(it, "guid", ns) or _t(it, "a:id", ns) or link,
                url=link, title=title.split(" - ")[0].strip() if company else title,
                company=company, location=location,
                remote_flag="remote" in (title + " " + desc).lower(),
                salary_min=smin, salary_max=smax, description=desc[:4000], posted_at=date,
            ))
        return roles

    @staticmethod
    def _guess(title: str, desc: str) -> tuple[str | None, str | None]:
        # Boards commonly format "Title - Company - Location" or put "Company: X" in the body
        parts = [p.strip() for p in title.split(" - ")]
        company = parts[1] if len(parts) >= 2 else None
        location = parts[2] if len(parts) >= 3 else None
        if not location:
            m = re.search(r"\b(Location|Based)\s*[:\-]\s*([A-Z][A-Za-z ,]+)", desc)
            location = m.group(2).strip() if m else None
        return company, location

    @staticmethod
    def _salary(desc: str) -> tuple[int | None, int | None]:
        vals = []
        for m in _SAL.finditer(desc):
            n = int(m.group(1) + (m.group(2) or ""))
            if m.group(3) or n < 1000:
                n *= 1000
            if 20000 <= n <= 300000:
                vals.append(n)
        if not vals:
            return None, None
        return min(vals), max(vals)


_XML_OK = {"amp", "lt", "gt", "quot", "apos"}
_ENT = re.compile(r"&([a-zA-Z][a-zA-Z0-9]*);")


def _xml_safe(text: str) -> str:
    """Feeds often contain HTML named entities (&pound; &nbsp;) that XML parsers reject. Convert to numeric refs."""
    def fix(m):
        name = m.group(1)
        if name in _XML_OK:
            return m.group(0)
        ch = html.unescape(m.group(0))
        return m.group(0) if ch == m.group(0) else "".join(f"&#{ord(c)};" for c in ch)
    return _ENT.sub(fix, text)


def _t(el, tag, ns) -> str:
    f = el.find(tag, ns) if ":" in tag else el.find(tag)
    return (f.text or "").strip() if f is not None and f.text else ""
