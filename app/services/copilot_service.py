import logging
import re
from copy import deepcopy
from time import perf_counter
from uuid import UUID

from app.core.config import Settings
from app.core.exceptions import (
    ClarificationRequired, CopilotError, InvalidPlannerDecisionError,
    InvalidToolArgumentsError, SpringBootError, UnknownToolError,
)
from app.core.text import contains_sensitive, display_text, normalize
from app.schemas.chat import ChatRequest, ChatResponse, ToolCallSummary
from app.schemas.conversation import ConversationState, PendingClarification, ResourceReference
from app.schemas.planner import ConversationReference, PlannerDecision
from app.schemas.spring import SpringPage
from app.schemas.tools import ToolName
from app.services.conversation_service import (
    AuthenticatedPrincipalResolver, ConversationService, ordinal_position, references, resolve_reference,
)
from app.services.planner import PlannerService, REFERENCE_TARGETS, TOOL_FIELDS, policy_action
from app.services.property_type_resolver import PropertyTypeResolver, normalized_label
from app.services.response_service import INCOME_NOTICE, READ_ONLY_ANSWER, UNSUPPORTED_ANSWER, ResponseService
from app.tools.registry import ToolRegistry

logger = logging.getLogger("habi.copilot")


class CopilotService:
    def __init__(
        self, principal: AuthenticatedPrincipalResolver, conversations: ConversationService,
        planner: PlannerService, registry: ToolRegistry, types: PropertyTypeResolver,
        responses: ResponseService, settings: Settings,
    ):
        self._principal = principal
        self._conversations = conversations
        self._planner = planner
        self._registry = registry
        self._types = types
        self._responses = responses
        self._settings = settings

    async def chat(self, request: ChatRequest, *, authorization: str) -> tuple[ChatResponse, int]:
        cid = None
        calls: list[ToolCallSummary] = []
        try:
            # Toujours avant toute lecture mémoire ou appel Groq.
            scope = await self._principal.resolve(authorization=authorization)
            async with self._conversations.turn(request.conversation_id, scope=scope) as conversation:
                cid = conversation.conversation_id
                state = conversation.state
                secrets = (authorization, authorization.removeprefix("Bearer "), self._settings.groq_api_key.get_secret_value())
                if contains_sensitive(request.message, secrets):
                    response = ChatResponse(status="UNSUPPORTED", answer="Retirez les secrets, coordonnées et liens de votre message, puis posez votre question métier.")
                else:
                    response = await self._answer(request.message, state, authorization, calls, cid)
                    await self._conversations.save(conversation, scope=scope)
                response.conversation_id = cid
                response.tool_calls = calls
                logger.info("conversationId=%s status=%s", cid, response.status)
                return response, 200
        except (SpringBootError, CopilotError) as exc:
            logger.warning("conversationId=%s status=ERROR error=%s", cid, exc.code)
            return ChatResponse(conversation_id=cid, status="ERROR", answer=exc.message, error_code=exc.code, tool_calls=calls), exc.status_code
        except (InvalidToolArgumentsError, UnknownToolError):
            error = InvalidPlannerDecisionError()
            logger.warning("conversationId=%s status=ERROR error=%s", cid, error.code)
            return ChatResponse(conversation_id=cid, status="ERROR", answer=error.message, error_code=error.code, tool_calls=calls), error.status_code
        except Exception:
            # Frontière HTTP : jamais de payload, secret, traceback ou repr d'exception.
            logger.error("conversationId=%s status=ERROR error=INTERNAL_ERROR", cid)
            return ChatResponse(conversation_id=cid, status="ERROR", answer="Une erreur interne empêche de traiter la demande.", error_code="INTERNAL_ERROR", tool_calls=calls), 500

    async def _answer(self, message: str, state: ConversationState, authorization: str,
                      calls: list[ToolCallSummary], cid: UUID) -> ChatResponse:
        start = perf_counter()
        action = policy_action(message)
        decision, chosen_type = self._pending_decision(message, state) if not action else (None, None)
        from_pending = decision is not None
        if action:
            decision = PlannerDecision(action=action)
        if decision is None:
            try:
                decision = await self._planner.plan(message, state)
            finally:
                logger.info("conversationId=%s planner_ms=%.1f", cid, (perf_counter() - start) * 1000)
        logger.info("conversationId=%s action=%s", cid, decision.action)
        if decision.action == "READ_ONLY_REFUSAL":
            state.pending_clarification = None
            return ChatResponse(status="READ_ONLY", answer=READ_ONLY_ANSWER)
        if decision.action == "UNSUPPORTED":
            state.pending_clarification = None
            return ChatResponse(status="UNSUPPORTED", answer=UNSUPPORTED_ANSWER)
        if decision.action == "NEEDS_CLARIFICATION":
            if not from_pending:
                state.pending_clarification = None
            return ChatResponse(status="NEEDS_CLARIFICATION", answer="Pouvez-vous préciser le bien, le propriétaire, la candidature ou l'information souhaitée ?")
        if decision.action == "ANSWER_FROM_CONTEXT":
            if decision.field == "incomeVerification":
                return ChatResponse(status="ANSWERED", answer=INCOME_NOTICE)
            if state.last_tool is None:
                return ChatResponse(status="NEEDS_CLARIFICATION", answer="Votre question concerne-t-elle les biens, les propriétaires ou les candidatures ?")
            # Relecture autorisée, pas de restitution de faits privés périmés.
            name = str(state.last_tool)
            arguments = deepcopy(state.last_arguments)
            if decision.field not in TOOL_FIELDS[name]:
                return ChatResponse(status="NEEDS_CLARIFICATION", answer="Précisez la ressource à consulter pour cette information.")
        else:
            self._planner.validate(decision)
            name = decision.tool.value
            arguments = deepcopy(decision.arguments)
            if decision.reference:
                try:
                    identifier = resolve_reference(decision.reference, state, message)
                except ClarificationRequired:
                    state.pending_clarification = PendingClarification(kind="resource", entity=decision.reference.entity, decision=decision)
                    # Ne pas réexposer d'anciens labels privés sans relecture Spring.
                    return ChatResponse(status="NEEDS_CLARIFICATION", answer="La référence est absente ou ambiguë. Indiquez le numéro dans la dernière liste affichée, ou demandez une nouvelle recherche.")
                arguments[REFERENCE_TARGETS[name][1]] = identifier
            if decision.propertyTypeLabel:
                # Le catalogue technique est consulté seulement après validation locale.
                matches = await self._types.match(decision.propertyTypeLabel, authorization=authorization)
                if chosen_type is not None:
                    matches = [item for item in matches if item.id == chosen_type]
                if len(matches) != 1:
                    options = [ResourceReference(id=item.id, label=display_text(item.label)) for item in matches[:10]]
                    state.pending_clarification = PendingClarification(kind="type", decision=decision, type_options=options)
                    text = "Quel type immobilier souhaitez-vous ?" if matches else "Ce libellé ne correspond à aucun type du catalogue. Précisez le type immobilier."
                    if options:
                        text += "\n" + "\n".join(f"{i}. {item.label}" for i, item in enumerate(options, 1))
                    return ChatResponse(status="NEEDS_CLARIFICATION", answer=text)
                if name == "search_my_properties":
                    arguments.setdefault("filters", {})
                    if arguments["filters"] is None:
                        arguments["filters"] = {}
                    arguments["filters"]["typeId"] = matches[0].id
                else:
                    arguments["typeId"] = matches[0].id

        # Revalidation finale des paramètres après résolution Python.
        self._registry.validate_arguments(name, arguments)
        if len(calls) >= min(1, self._settings.copilot_max_tool_calls):
            raise InvalidPlannerDecisionError()
        start = perf_counter()
        calls.append(ToolCallSummary(name=name))
        try:
            result = await self._registry.execute_tool(name, arguments, authorization)
        finally:
            logger.info("conversationId=%s tool=%s tool_ms=%.1f", cid, name, (perf_counter() - start) * 1000)
        self._conversations.remember(state, name, arguments, result, decision.field)
        state.pending_clarification = None

        if isinstance(result, SpringPage) and decision.expectSingle and result.content:
            entity = "owner" if name == "search_my_owners" else "application" if name == "search_my_applications" else "property"
            if entity == "property" and result.totalElements == 1:
                answer = self._responses.render("get_property_details", result.content[0], decision.field)
                return self._rendered(answer)
            target = {"property": "get_property_details", "application": "get_application_details", "owner": "get_owner_portfolio"}[entity]
            pending = PlannerDecision(
                action="CALL_TOOL", tool=ToolName(target), field=decision.field,
                reference=ConversationReference(entity=entity, kind="SELECTED"),
            )
            state.pending_clarification = PendingClarification(kind="resource", entity=entity, decision=pending)
            listing = self._responses.render(name, result, "summary")
            return ChatResponse(status="NEEDS_CLARIFICATION", answer=f"{listing}\nLequel souhaitez-vous consulter ? Répondez par son numéro.")
        if isinstance(result, SpringPage) and not result.content:
            return self._rendered(self._responses.render(name, result, "summary"))
        return self._rendered(self._responses.render(name, result, decision.field))

    @staticmethod
    def _rendered(answer: str | None) -> ChatResponse:
        if answer is None:
            return ChatResponse(status="UNSUPPORTED", answer="Cette information n'est pas disponible avec cette consultation. Précisez votre question ou sélectionnez une ressource.")
        return ChatResponse(status="ANSWERED", answer=answer)

    @staticmethod
    def _pending_decision(message: str, state: ConversationState) -> tuple[PlannerDecision | None, int | None]:
        pending = state.pending_clarification
        if pending is None:
            return None, None
        items = pending.type_options if pending.kind == "type" else references(state, pending.entity)
        position = ordinal_position(message, len(items))
        # Une réponse courte de sélection reprend la question précédente, sans LLM.
        bare_selection = bool(re.fullmatch(r"(?:le |la |numero |n° ?)?(?:\d{1,2}(?:e|eme)?|premier|premiere|deuxieme|second|seconde|troisieme|quatrieme|cinquieme|sixieme|septieme|huitieme|neuvieme|dixieme|dernier|derniere)[ .!?]*", normalize(message)))
        if bare_selection:
            if position is None or not 1 <= position <= len(items):
                return PlannerDecision(action="NEEDS_CLARIFICATION"), None
            decision = pending.decision.model_copy(deep=True)
            if pending.kind == "type":
                return decision, items[position - 1].id
            decision.reference = ConversationReference(entity=pending.entity, kind="POSITION", position=position)
            return decision, None
        if pending.kind == "type":
            exact = [item for item in items if normalized_label(item.label) == normalized_label(message)]
            if len(exact) == 1:
                return pending.decision.model_copy(deep=True), exact[0].id
            if not items and len(message.split()) <= 3 and "?" not in message:
                decision = pending.decision.model_copy(deep=True)
                decision.propertyTypeLabel = message
                return decision, None
        return None, None
