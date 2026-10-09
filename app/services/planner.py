import json
import re
from copy import deepcopy

from pydantic import ValidationError

from app.clients.llm_client import LLMClient
from app.core.exceptions import InvalidPlannerDecisionError, InvalidToolArgumentsError, UnknownToolError
from app.core.text import normalize
from app.prompts.planner import SYSTEM_PROMPT
from app.schemas.conversation import ConversationState
from app.schemas.planner import PlannerDecision
from app.tools.registry import ToolRegistry


def policy_action(message: str) -> str | None:
    text = normalize(message)
    if re.search(
        r"\b(accepte(?:r|z)?|rejette(?:r|z)?|rejeter|modifie(?:r|z)?|publie(?:r|z)?|supprime(?:r|z)?"
        r"|ajoute(?:r|z)?|annule(?:r|z)?|cree(?:r|z)?|valide(?:r|z)?|change(?:r|z)?"
        r"|accept|reject|delete|update|publish)\b", text
    ):
        return "READ_ONLY_REFUSAL"
    if re.search(r"solvabilite|scor(?:e|ing)|risque d.impay|meilleur candidat|class(?:e|er|ement).*(?:candidat|merite)|recommand.*(?:accept|candidat)|quel candidat.*(?:choisir|accepter)", text):
        return "UNSUPPORTED"
    return None


REFERENCE_TARGETS = {
    "get_property_details": ("property", "id"),
    "get_application_details": ("application", "id"),
    "get_owner_portfolio": ("owner", "id"),
    "search_my_applications": ("property", "propertyId"),
}

PROPERTY_FIELDS = {"summary", "status", "rent", "deposit", "area", "rooms", "bedrooms", "bathrooms", "furnished", "sharedHousingAllowed", "availableFrom"}
APPLICATION_FIELDS = {"summary", "status", "rent", "monthlyIncomeDeclared", "profession", "professionalSituation", "documents", "completeness", "incomeVerification"}
TOOL_FIELDS = {
    "get_property_details": PROPERTY_FIELDS,
    "get_application_details": APPLICATION_FIELDS,
    "search_my_properties": {"summary", "total"},
    "get_owner_portfolio": {"summary", "total"},
    "search_my_applications": {"summary", "total"},
    "search_my_owners": {"summary", "total"},
    "get_portfolio_kpis": {"summary", "total", "available", "rented", "draft", "unavailable", "averageRent", "distributionByType", "distributionByCity", "distributionByNeighborhood"},
    "get_application_kpis": {"summary", "total", "pending", "underReview", "accepted", "rejected", "cancelled", "receivedThisWeek", "receivedThisMonth", "applicationsByProperty", "topPropertiesByApplications", "propertiesWithoutApplications"},
}


def has_identifier(arguments: dict) -> bool:
    return any(key in {"id", "propertyId", "typeId", "ownerId", "agencyId", "userId"}
               or (isinstance(value, dict) and has_identifier(value))
               for key, value in arguments.items())


class PlannerService:
    def __init__(self, llm: LLMClient, registry: ToolRegistry):
        self._llm = llm
        self._registry = registry
        catalog = [{"name": t.name.value, "description": t.description,
                    "arguments": t.arguments_model.model_json_schema()} for t in registry.list_tools()]
        self._prompt = SYSTEM_PROMPT + "\nCATALOGUE AUTORISÉ :\n" + json.dumps(catalog, ensure_ascii=False)

    def validate(self, decision: PlannerDecision) -> None:
        if decision.action != "CALL_TOOL":
            return
        name = decision.tool.value
        self._registry.get(name)
        fields = TOOL_FIELDS[name]
        if decision.expectSingle and name == "search_my_properties":
            fields = fields | PROPERTY_FIELDS
        if decision.expectSingle and name == "search_my_applications":
            fields = fields | APPLICATION_FIELDS
        if decision.field not in fields:
            raise InvalidPlannerDecisionError()
        if has_identifier(decision.arguments):
            raise InvalidPlannerDecisionError()
        arguments = deepcopy(decision.arguments)
        target = REFERENCE_TARGETS.get(name)
        if decision.reference:
            if target is None or decision.reference.entity != target[0]:
                raise InvalidPlannerDecisionError()
            arguments[target[1]] = 1  # Validation locale, jamais envoyé au réseau.
        if name in {"get_property_details", "get_application_details", "get_owner_portfolio"} and not decision.reference:
            raise InvalidPlannerDecisionError()
        if decision.propertyTypeLabel and name not in {"search_my_properties", "get_owner_portfolio"}:
            raise InvalidPlannerDecisionError()
        self._registry.validate_arguments(name, arguments)

    async def plan(self, message: str, state: ConversationState) -> PlannerDecision:
        action = policy_action(message)
        if action:
            return PlannerDecision(action=action)
        # Aucun id, label Spring, revenu, dossier, principal ou historique brut.
        context = {
            "last_tool": state.last_tool,
            "last_field": state.last_field,
            "listed_counts": {"property": len(state.last_properties), "application": len(state.last_applications), "owner": len(state.last_owners)},
            "selected": {"property": state.selected_property_id is not None,
                         "application": state.selected_application_id is not None,
                         "owner": state.selected_owner_id is not None},
            "pending_entity": state.pending_clarification.entity if state.pending_clarification else None,
        }
        payload = json.dumps({"question": message, "context": context}, ensure_ascii=False)
        schema = PlannerDecision.model_json_schema()
        # Une tentative initiale et UNE réparation, sans renvoyer la sortie invalide.
        for attempt in range(2):
            try:
                prompt = self._prompt
                if attempt:
                    prompt += "\nRÉPARATION UNIQUE : respecte exactement le schéma et les arguments autorisés. N'invente aucun id."
                content = await self._llm.generate(system_prompt=prompt, user_message=payload, schema=schema)
                decision = PlannerDecision.model_validate_json(content)
                self.validate(decision)
                return decision
            except (ValidationError, InvalidPlannerDecisionError, InvalidToolArgumentsError, UnknownToolError):
                pass
        raise InvalidPlannerDecisionError()
