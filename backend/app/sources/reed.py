"""Reed.co.uk Jobseeker API. Free key from https://www.reed.co.uk/developers/jobseeker
Auth is HTTP basic with the key as username and an empty password."""
import asyncio
import httpx

from .base import RawRole, Source

BASE = "https://www.reed.co.uk/api/1.0"


class ReedSource(Source):
    name = "reed"
    kind = "api"

    async def fetch(self) -> list[RawRole]:
        key = self.env.get("CAREER_REED_KEY")
        if not key:
            self.error = "CAREER_REED_KEY not set"
            return []
        base = self.env.get("CAREER_REED_BASE", BASE)
        out: list[RawRole] = []
        try:
            async with httpx.AsyncClient(auth=(key, ""), timeout=30) as client:
                for term in self.terms:
                    r = await client.get(
                        f"{base}/search",
                        params={"keywords": term, "resultsToTake": 50, "distanceFromLocation": 30},
                    )
                    r.raise_for_status()
                    for j in r.json().get("results", []):
                        out.append(self._to_role(j))
                    await asyncio.sleep(0.3)
        except Exception as e:  # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"[:300]
        return out

    @staticmethod
    def _to_role(j: dict) -> RawRole:
        loc = j.get("locationName") or ""
        return RawRole(
            external_id=str(j.get("jobId")),
            url=j.get("jobUrl") or "",
            title=j.get("jobTitle") or "",
            company=j.get("employerName"),
            location=loc,
            remote_flag="remote" in (loc + " " + (j.get("jobDescription") or "")).lower(),
            salary_min=_int(j.get("minimumSalary")),
            salary_max=_int(j.get("maximumSalary")),
            salary_text=None,
            description=j.get("jobDescription"),
            posted_at=j.get("date"),
        )


def _int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
