"""Résolution d'identité interne ; aucune conversation n'est encore ouverte."""

from typing import Protocol

from app.clients.spring_client import SpringBootClient


class AuthenticatedPrincipalResolver(Protocol):
    async def resolve(self, *, authorization: str) -> str:
        """Retourne un scope interne établi par une autorité de confiance."""
        ...


class SpringAuthenticatedPrincipalResolver:
    def __init__(self, client: SpringBootClient):
        self._client = client

    async def resolve(self, *, authorization: str) -> str:
        account = await self._client.get_current_account(authorization=authorization)
        # id vient de /auth/me après validation Spring, jamais du body/claims locaux.
        return f"habiterra:account:{account.id}"
