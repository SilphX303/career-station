"""Adzuna Jobs API. Free app_id and app_key from https://developer.adzuna.com"""
import asyncio
import httpx

from .base import RawRole, Source

BASE = "https://api.adzuna.com/v1/api/jobs/gb/search/1"


class AdzunaSource(Source):
    name = "adzuna"
    kind = "api"

    async def fetch(self) -> list[RawRole]:
        app_id = self.env.get("CAREER_ADZUNA_ID")
        key = self.env.get("CAREER_ADZUNA_KEY")
        if not (app_id and key):
            self.error = "CAREER_ADZUNA_ID / CAREER_ADZUNA_KEY not set"
            return []
        base = self.env.get("CAREER_ADZUNA_BASE", BASE)
        out: list[RawRole] = []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                for term in self.terms:
                    r = await client.get(base, params={
                        "app_id": app_id, "app_key": key, "what": term, "where": "UK",
                        "results_per_page": 50, "max_days_old": 14, "content-type": "application/json",
                    })
                    r.raise_for_status()
                    for j in r.json().get("results", []):
                        out.append(self._to_role(j))
                    await asyncio.sleep(0.5)
        except Exception as e:  # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"[:300]
        return out

    @staticmethod
    def _to_role(j: dict) -> RawRole:
        loc = (j.get("location") or {}).get("display_name") or ""
        desc = j.get("description") or ""
        return RawRole(
            external_id=str(j.get("id")),
            url=j.get("redirect_url") or "",
            title=j.get("title") or "",
            company=(j.get("company") or {}).get("display_name"),
            location=loc,
            remote_flag="remote" in (loc + " " + desc).lower(),
            salary_min=_int(j.get("salary_min")),
            salary_max=_int(j.get("salary_max")),
            salary_text="estimated" if j.get("salary_is_predicted") == "1" else None,
            description=desc,
            posted_at=j.get("created"),
        )


def _int(v):
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None
