from .base import RawRole, Source
from .reed import ReedSource

REGISTRY: dict[str, type[Source]] = {
    ReedSource.name: ReedSource,
}

__all__ = ["RawRole", "Source", "REGISTRY"]
