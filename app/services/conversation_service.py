"""Identité de confiance, sérialisation des tours et références compactes."""

import asyncio
import re
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.clients.spring_client import SpringBootClient
from app.core.exceptions import ClarificationRequired, ConversationUnavailableError
from app.core.text import display_text, normalize
from app.memory.models import Conversation
from app.memory.store import ConversationStore
from app.schemas.conversation import ConversationState, ResourceReference
from app.schemas.planner import ConversationReference, Focus
from app.schemas.tools import ToolName


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


def ordinal_position(message: str, count: int) -> int | None:
    text = normalize(message).strip(" .!?")
    ordinals = {"premier": 1, "premiere": 1, "deuxieme": 2, "second": 2, "seconde": 2,
                "troisieme": 3, "quatrieme": 4, "cinquieme": 5, "sixieme": 6,
                "septieme": 7, "huitieme": 8, "neuvieme": 9, "dixieme": 10}
    for word, position in ordinals.items():
        if re.search(rf"\b{word}\b", text):
            return position
    if re.search(r"\bderni(?:er|ere)\b", text):
        return count or None
    match = re.fullmatch(r"(?:le |la |numero |n° ?)?(\d{1,2})(?:e|eme)?", text)
    return int(match.group(1)) if match else None


def references(state: ConversationState, entity: str) -> list[ResourceReference]:
    return getattr(state, {"property": "last_properties", "application": "last_applications", "owner": "last_owners"}[entity])


def resolve_reference(reference: ConversationReference, state: ConversationState, message: str) -> int:
    items = references(state, reference.entity)
    if reference.kind == "EXPLICIT":
        ids = re.findall(r"(?:\bid\b|\bidentifiant\b|#)\s*[:=]?\s*(\d+)", normalize(message))
        if str(reference.explicitId) not in ids:
            raise ClarificationRequired()
        return reference.explicitId
    if reference.kind in {"POSITION", "LAST"}:
        position = len(items) if reference.kind == "LAST" else reference.position
        stated = ordinal_position(message, len(items))
        if stated is None or stated != position or not 1 <= position <= len(items):
            raise ClarificationRequired()
        return items[position - 1].id
    selected = getattr(state, f"selected_{reference.entity}_id")
    if selected is not None:
        return selected
    if len(items) == 1:
        return items[0].id
    raise ClarificationRequired()


class ConversationService:
    def __init__(self, store: ConversationStore):
        self._store = store
        self._locks: dict[tuple[str, UUID], tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def turn(self, conversation_id: UUID | None, *, scope: str) -> AsyncIterator[Conversation]:
        if conversation_id is None:
            conversation = await self._store.create(scope=scope)
            conversation_id = conversation.conversation_id
        key = (scope, conversation_id)
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            async with lock:
                conversation = await self._store.get(conversation_id, scope=scope)
                if conversation is None:
                    # Même erreur pour absent, expiré et appartenant à autrui.
                    raise ConversationUnavailableError()
                yield conversation
        finally:
            _, users = self._locks[key]
            if users == 1:
                del self._locks[key]
            else:
                self._locks[key] = (lock, users - 1)

    async def save(self, conversation: Conversation, *, scope: str) -> None:
        conversation.state.updated_at = datetime.now(timezone.utc)
        saved = await self._store.update_state(conversation.conversation_id, conversation.state, scope=scope)
        if saved is None:
            raise ConversationUnavailableError()

    @staticmethod
    def remember(state: ConversationState, name: str, arguments: dict, result, field: Focus = "summary") -> None:
        state.last_tool = ToolName(name)
        state.last_field = field
        state.last_arguments = arguments.copy()
        state.last_facts = {}
        # On conserve les références AFFICHÉES, pas le dossier ou la réponse brute.
        entity = {"search_my_properties": "property", "get_owner_portfolio": "property",
                  "search_my_applications": "application", "search_my_owners": "owner"}.get(name)
        if entity:
            refs = []
            for item in result.content[:10]:
                identifier = item.ownerId if entity == "owner" else item.id
                label = item.displayName if entity == "owner" else item.candidateLabel if entity == "application" else item.title
                refs.append(ResourceReference(id=identifier, label=display_text(label)))
            setattr(state, {"property": "last_properties", "application": "last_applications", "owner": "last_owners"}[entity], refs)
            setattr(state, f"selected_{entity}_id", refs[0].id if len(refs) == 1 and result.totalElements == 1 else None)
            state.last_facts = {"total": result.totalElements}
        if name == "get_owner_portfolio":
            state.selected_owner_id = arguments["id"]
        if name == "get_property_details":
            state.selected_property_id = arguments["id"]
        if name == "get_application_details":
            state.selected_application_id = arguments["id"]
        if name in {"get_portfolio_kpis", "get_application_kpis"}:
            state.last_facts = {k: v for k, v in result.model_dump().items() if isinstance(v, (int, float)) or v is None}
        if name == "get_application_kpis" and field in {"applicationsByProperty", "topPropertiesByApplications", "propertiesWithoutApplications"}:
            data = getattr(result, field)
            rows = data if isinstance(data, list) else data.content
            state.last_properties = [ResourceReference(id=row.propertyId, label=display_text(row.title)) for row in rows[:10]]
            state.selected_property_id = None
