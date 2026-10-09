from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.conversation import ConversationState


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    conversation_id: UUID = Field(alias="conversationId")
    principal_id: str
    created_at: datetime
    expires_at: datetime
    state: ConversationState = Field(default_factory=ConversationState)
