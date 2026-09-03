from .adzuna import AdzunaSource
from .base import RawRole, Source
from .linkedin import LinkedInSource
from .reed import ReedSource
from .rss import RssSource

REGISTRY: dict[str, type[Source]] = {
    ReedSource.name: ReedSource,
    AdzunaSource.name: AdzunaSource,
    RssSource.name: RssSource,
    LinkedInSource.name: LinkedInSource,
}

__all__ = ["RawRole", "Source", "REGISTRY"]
