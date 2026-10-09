from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=10000)
    conversation_id: UUID | None = Field(default=None, alias="conversationId")


class ToolCallSummary(BaseModel):
    name: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: UUID | None = Field(default=None, alias="conversationId")
    status: Literal["ANSWERED", "NEEDS_CLARIFICATION", "READ_ONLY", "UNSUPPORTED", "ERROR"]
    answer: str
    tool_calls: list[ToolCallSummary] = Field(default_factory=list, alias="toolCalls")
    suggestions: list[str] = Field(default_factory=list)
    error_code: str | None = Field(default=None, alias="errorCode")
