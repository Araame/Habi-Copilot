from typing import Protocol


class LLMClient(Protocol):
    """Abstraction fournisseur ; aucun appel Groq à cette étape."""

    async def generate(self, *, system_prompt: str, user_message: str) -> str:
        ...
