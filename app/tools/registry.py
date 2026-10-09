import json
from types import MappingProxyType

from pydantic import BaseModel, JsonValue, ValidationError

from app.clients.spring_client import SpringBootClient, require_authorization
from app.core.exceptions import InvalidToolArgumentsError, UnknownToolError
from app.schemas.tools import ToolDefinition
from app.tools import applications, kpis, owners, properties

class ToolRegistry:
    """Catalogue fermé ; les handlers sont des méthodes Spring explicites."""

    def __init__(self, client: SpringBootClient):
        self._tools = MappingProxyType({
            tool.name.value: tool
            for tool in (
                *properties.definitions(client), *owners.definitions(client),
                *applications.definitions(client), *kpis.definitions(client),
            )
        })

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError("Outil inconnu.") from None

    def list_tools(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools.values())

    def validate_arguments(self, tool_name: str, arguments: dict[str, JsonValue]) -> BaseModel:
        definition = self.get(tool_name)  # Toujours avant le réseau.
        invalid = False
        try:
            # Le mode JSON strict accepte les dates ISO/enums JSON sans convertir
            # une chaîne numérique en entier, ni un entier en booléen.
            validated = definition.arguments_model.model_validate_json(
                json.dumps(arguments, allow_nan=False)
            )
        except (ValidationError, TypeError, ValueError):
            invalid = True
        if invalid:
            raise InvalidToolArgumentsError("Arguments invalides pour cet outil.")
        return validated

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, JsonValue], authorization: str
    ) -> BaseModel:
        definition = self.get(tool_name)
        validated = self.validate_arguments(tool_name, arguments)
        require_authorization(authorization)
        return await definition.handler(validated, authorization)
