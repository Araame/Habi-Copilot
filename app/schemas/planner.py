"""La décision ne contient aucune réponse métier générée par le modèle."""

from typing import Literal, Self

from pydantic import Field, JsonValue, model_validator

from app.schemas.spring import StrictRequest
from app.schemas.tools import ToolName

Action = Literal["CALL_TOOL", "NEEDS_CLARIFICATION", "ANSWER_FROM_CONTEXT", "READ_ONLY_REFUSAL", "UNSUPPORTED"]
Entity = Literal["property", "application", "owner"]
Focus = Literal[
    "summary", "total", "status", "rent", "deposit", "area", "rooms", "bedrooms",
    "bathrooms", "availableFrom", "furnished", "sharedHousingAllowed",
    "available", "rented", "draft", "unavailable", "averageRent",
    "distributionByType", "distributionByCity", "distributionByNeighborhood",
    "pending", "underReview", "accepted", "rejected", "cancelled", "receivedThisWeek",
    "receivedThisMonth", "applicationsByProperty", "topPropertiesByApplications",
    "propertiesWithoutApplications", "monthlyIncomeDeclared", "profession",
    "professionalSituation", "documents", "completeness", "incomeVerification",
]


class ConversationReference(StrictRequest):
    entity: Entity
    kind: Literal["POSITION", "LAST", "SELECTED", "EXPLICIT"]
    position: int | None = Field(default=None, ge=1, le=10)
    explicitId: int | None = Field(default=None, gt=0, le=9223372036854775807)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.kind == "POSITION") != (self.position is not None):
            raise ValueError("Une position est requise uniquement pour POSITION.")
        if (self.kind == "EXPLICIT") != (self.explicitId is not None):
            raise ValueError("Un id explicite est requis uniquement pour EXPLICIT.")
        return self


class PlannerDecision(StrictRequest):
    action: Action
    tool: ToolName | None = None
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    reference: ConversationReference | None = None
    propertyTypeLabel: str | None = Field(default=None, min_length=1, max_length=255)
    field: Focus = "summary"
    expectSingle: bool = False
    clarificationQuestion: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.action == "CALL_TOOL":
            if self.tool is None or self.clarificationQuestion is not None:
                raise ValueError("CALL_TOOL exige un outil et aucune question libre.")
        elif self.tool is not None or self.arguments or self.reference or self.propertyTypeLabel or self.expectSingle:
            raise ValueError("Seul CALL_TOOL accepte un outil, des arguments ou une référence.")
        if self.clarificationQuestion is not None and self.action != "NEEDS_CLARIFICATION":
            raise ValueError("Question réservée à NEEDS_CLARIFICATION.")
        return self
