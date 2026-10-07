from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=10000)
    conversation_id: UUID | None = Field(default=None, alias="conversationId")


class NotImplementedResponse(BaseModel):
    status: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"
    message: str = "L'orchestration du Copilot n'est pas encore implémentée."
