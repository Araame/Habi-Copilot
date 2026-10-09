import asyncio
import logging
from typing import Protocol

from groq import APIConnectionError, APIStatusError, APITimeoutError, AsyncGroq

from app.core.config import Settings
from app.core.exceptions import (
    InvalidPlannerDecisionError, LLMConfigurationError, LLMTimeoutError, LLMUnavailableError,
)


class LLMClient(Protocol):
    """Le reste de l'application ignore le SDK du fournisseur."""

    async def generate(self, *, system_prompt: str, user_message: str, schema: dict) -> str:
        ...


class GroqLLMClient:
    def __init__(self, settings: Settings):
        # GROQ_LOG=debug peut journaliser les options et le prompt. Les durées et
        # catégories utiles sont déjà émises par notre logger, jamais par le SDK.
        for name in ("groq", "httpx", "httpcore"):
            external = logging.getLogger(name)
            external.handlers = [logging.NullHandler()]
            external.propagate = False
        self._model = settings.copilot_llm_model.strip()
        self._timeout = settings.copilot_llm_timeout_seconds
        key = settings.groq_api_key.get_secret_value()
        self._client = AsyncGroq(api_key=key, timeout=self._timeout, max_retries=0) if key and self._model else None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def generate(self, *, system_prompt: str, user_message: str, schema: dict) -> str:
        if self._client is None:
            raise LLMConfigurationError()
        error = None
        try:
            # Borne totale par tentative, en plus du timeout HTTP du SDK.
            async with asyncio.timeout(self._timeout):
                result = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    response_format={"type": "json_schema", "json_schema": {
                        "name": "planner_decision", "strict": False, "schema": schema,
                    }},
                    temperature=0,
                    max_completion_tokens=2048,
                )
        except (APITimeoutError, TimeoutError):
            error = LLMTimeoutError()
        except APIConnectionError:
            error = LLMUnavailableError()
        except APIStatusError as exc:
            if getattr(exc, "code", None) == "json_validate_failed":
                error = InvalidPlannerDecisionError()
            elif exc.status_code in (400, 401, 403, 404):
                error = LLMConfigurationError()
            else:
                error = LLMUnavailableError()
        if error is not None:
            raise error
        if not result.choices or result.choices[0].finish_reason != "stop":
            raise InvalidPlannerDecisionError()
        content = result.choices[0].message.content
        if not content or len(content) > 20000:
            raise InvalidPlannerDecisionError()
        return content
