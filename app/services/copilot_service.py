from app.core.exceptions import CopilotNotImplementedError
from app.schemas.chat import ChatRequest


class CopilotService:
    async def chat(self, request: ChatRequest) -> None:
        raise CopilotNotImplementedError
