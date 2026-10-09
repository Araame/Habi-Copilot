from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from app.schemas.planner import Entity, Focus, PlannerDecision
from app.schemas.tools import ToolName


class ResourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    label: str = Field(max_length=160)


class PendingClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["resource", "type"]
    entity: Entity | None = None
    decision: PlannerDecision
    type_options: list[ResourceReference] = Field(default_factory=list, max_length=10)


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_tool: ToolName | None = None
    last_field: Focus = "summary"
    last_arguments: dict[str, JsonValue] = Field(default_factory=dict)
    last_properties: list[ResourceReference] = Field(default_factory=list, max_length=10)
    last_applications: list[ResourceReference] = Field(default_factory=list, max_length=10)
    last_owners: list[ResourceReference] = Field(default_factory=list, max_length=10)
    selected_property_id: int | None = None
    selected_application_id: int | None = None
    selected_owner_id: int | None = None
    pending_clarification: PendingClarification | None = None
    last_facts: dict[str, int | float | bool | None] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
