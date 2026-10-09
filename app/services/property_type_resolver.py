import asyncio
from time import monotonic

from app.clients.spring_client import SpringBootClient
from app.core.text import normalize
from app.schemas.spring import PropertyType


def normalized_label(label: str) -> str:
    # Singulier/pluriel français simple, sans table d'identifiants ou de synonymes.
    return " ".join(word[:-1] if len(word) > 3 and word.endswith("s") else word for word in normalize(label).split())


class PropertyTypeResolver:
    def __init__(self, client: SpringBootClient, ttl_seconds: int = 300):
        self._client = client
        self._ttl = ttl_seconds
        self._expires = 0.0
        self._types: list[PropertyType] = []
        self._lock = asyncio.Lock()

    async def match(self, label: str, *, authorization: str) -> list[PropertyType]:
        async with self._lock:
            if monotonic() >= self._expires:
                catalog = await self._client.get_property_types(authorization=authorization)
                self._types = catalog.root
                self._expires = monotonic() + self._ttl
            target = normalized_label(label)
            exact = [item for item in self._types if normalized_label(item.label) == target]
            if exact:
                return exact
            words = set(target.split())
            return [item for item in self._types if words and words <= set(normalized_label(item.label).split())]
