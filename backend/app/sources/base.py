import hashlib
import re
from dataclasses import dataclass, field


@dataclass
class RawRole:
    external_id: str
    url: str
    title: str
    company: str | None = None
    location: str | None = None
    remote_flag: bool = False
    salary_min: int | None = None
    salary_max: int | None = None
    salary_text: str | None = None
    description: str | None = None
    posted_at: str | None = None
    extra: dict = field(default_factory=dict)

    def dedupe_hash(self) -> str:
        """Same role posted on two boards collapses to one record."""
        key = "|".join(_norm(x) for x in (self.title, self.company or "", self.location or ""))
        return hashlib.sha1(key.encode()).hexdigest()


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(ltd|limited|plc|uk|the)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


class Source:
    """One job board. fetch() must never raise; return [] and set error instead."""

    name: str = "base"
    kind: str = "api"

    def __init__(self, terms: list[str], env: dict):
        self.terms = terms
        self.env = env
        self.error: str | None = None

    async def fetch(self) -> list[RawRole]:
        raise NotImplementedError
