from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.memory.models import Conversation
from app.schemas.conversation import ConversationState


class ConversationStore(Protocol):
    """scope : clé interne issue d'une identité vérifiée, jamais du body/JWT brut."""

    async def create(self, *, scope: str) -> Conversation: ...
    async def get(self, conversation_id: UUID, *, scope: str) -> Conversation | None: ...
    async def update_state(
        self, conversation_id: UUID, state: ConversationState, *, scope: str
    ) -> Conversation | None: ...
    async def delete(self, conversation_id: UUID, *, scope: str) -> None: ...


class InMemoryConversationStore:
    """Mémoire par processus ; TTL fixe depuis la création, purge à chaque accès.

    Usage prévu sur une seule boucle asyncio. Le store n'est pas relié au chat.
    """

    def __init__(
        self, ttl_minutes: int = 30, *, clock: Callable[[], datetime] | None = None
    ):
        if ttl_minutes <= 0:
            raise ValueError("Le TTL doit être positif.")
        self._ttl = timedelta(minutes=ttl_minutes)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._conversations: dict[tuple[str, UUID], Conversation] = {}

    def _purge(self, scope: str) -> None:
        if not scope.strip():
            raise ValueError("Un scope interne non vide est requis.")
        now = self._clock()
        expired = [key for key, item in self._conversations.items() if item.expires_at <= now]
        for key in expired:
            del self._conversations[key]

    async def create(self, *, scope: str) -> Conversation:
        self._purge(scope)
        now = self._clock()
        conversation = Conversation(
            conversation_id=uuid4(), created_at=now, expires_at=now + self._ttl
        )
        self._conversations[(scope, conversation.conversation_id)] = conversation
        return conversation.model_copy(deep=True)

    async def get(self, conversation_id: UUID, *, scope: str) -> Conversation | None:
        self._purge(scope)
        conversation = self._conversations.get((scope, conversation_id))
        return conversation.model_copy(deep=True) if conversation else None

    async def update_state(
        self, conversation_id: UUID, state: ConversationState, *, scope: str
    ) -> Conversation | None:
        self._purge(scope)
        conversation = self._conversations.get((scope, conversation_id))
        if conversation is None:
            return None
        conversation.state = state.model_copy(deep=True)
        return conversation.model_copy(deep=True)

    async def delete(self, conversation_id: UUID, *, scope: str) -> None:
        self._purge(scope)
        self._conversations.pop((scope, conversation_id), None)
