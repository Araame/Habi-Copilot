import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, JsonValue, ValidationError

from app.core.config import Settings
from app.core.exceptions import (
    SpringBootError, SpringForbiddenError, SpringNotFoundError,
    SpringResponseError, SpringTimeoutError, SpringUnauthorizedError,
    SpringUnavailableError, SpringValidationError,
)
from app.schemas.spring import (
    ApplicationDetails, ApplicationKpis, ApplicationSearch, ApplicationSummary,
    CurrentAccount, OwnerSearch, OwnerSummary, PortfolioKpis, PropertyDetails,
    PropertySearch, SpringPage,
)
from app.schemas.tools import (
    GetApplicationDetailsArguments, GetApplicationKpisArguments,
    GetOwnerPortfolioArguments, GetPortfolioKpisArguments, GetPropertyDetailsArguments,
    SearchMyApplicationsArguments, SearchMyOwnersArguments, SearchMyPropertiesArguments,
)

R = TypeVar("R", bound=BaseModel)


def require_authorization(authorization: str) -> str:
    """Vérifie uniquement la syntaxe Bearer ; Spring valide le JWT et les droits."""
    if not isinstance(authorization, str) or not re.fullmatch(
        r"Bearer [A-Za-z0-9._~+/-]+=*", authorization
    ):
        raise SpringUnauthorizedError()
    return authorization


class SpringBootClient:
    """Seul point de communication Spring : huit opérations et /auth/me interne."""

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._client = httpx.AsyncClient(
            base_url=str(settings.spring_boot_base_url),
            timeout=settings.spring_boot_timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search_my_properties(
        self, arguments: SearchMyPropertiesArguments, authorization: str
    ) -> SpringPage[PropertyDetails]:
        return await self._request(
            "POST", "/api/v1/professional/properties/search", SpringPage[PropertyDetails],
            authorization=authorization,
            payload=arguments.model_dump(mode="json", include=set(PropertySearch.model_fields), exclude_none=True),
            params=arguments.model_dump(mode="json", include={"page", "size", "sort"}),
        )

    async def get_property_details(
        self, arguments: GetPropertyDetailsArguments, authorization: str
    ) -> PropertyDetails:
        return await self._request(
            "GET", f"/api/v1/professional/properties/{arguments.id}", PropertyDetails,
            authorization=authorization,
        )

    async def search_my_owners(
        self, arguments: SearchMyOwnersArguments, authorization: str
    ) -> SpringPage[OwnerSummary]:
        return await self._request(
            "POST", "/api/v1/professional/owners/search", SpringPage[OwnerSummary],
            authorization=authorization,
            payload=arguments.model_dump(mode="json", include=set(OwnerSearch.model_fields), exclude_none=True),
            params=arguments.model_dump(mode="json", include={"page", "size", "sort"}),
        )

    async def get_owner_portfolio(
        self, arguments: GetOwnerPortfolioArguments, authorization: str
    ) -> SpringPage[PropertyDetails]:
        # @ModelAttribute : filtres plats en query, aucun body ni objet filters.
        return await self._request(
            "GET", f"/api/v1/professional/owners/{arguments.id}/portfolio", SpringPage[PropertyDetails],
            authorization=authorization,
            params=arguments.model_dump(mode="json", exclude={"id"}, exclude_none=True),
        )

    async def search_my_applications(
        self, arguments: SearchMyApplicationsArguments, authorization: str
    ) -> SpringPage[ApplicationSummary]:
        return await self._request(
            "POST", "/api/v1/professional/applications/search", SpringPage[ApplicationSummary],
            authorization=authorization,
            payload=arguments.model_dump(mode="json", include=set(ApplicationSearch.model_fields), exclude_none=True),
            params=arguments.model_dump(mode="json", include={"page", "size", "sort"}),
        )

    async def get_application_details(
        self, arguments: GetApplicationDetailsArguments, authorization: str
    ) -> ApplicationDetails:
        return await self._request(
            "GET", f"/api/v1/professional/applications/{arguments.id}", ApplicationDetails,
            authorization=authorization,
        )

    async def get_portfolio_kpis(
        self, arguments: GetPortfolioKpisArguments, authorization: str
    ) -> PortfolioKpis:
        return await self._request(
            "GET", "/api/v1/professional/kpis/portfolio", PortfolioKpis,
            authorization=authorization,
        )

    async def get_application_kpis(
        self, arguments: GetApplicationKpisArguments, authorization: str
    ) -> ApplicationKpis:
        return await self._request(
            "GET", "/api/v1/professional/kpis/applications", ApplicationKpis,
            authorization=authorization, params=arguments.model_dump(mode="json"),
        )

    async def get_current_account(self, *, authorization: str) -> CurrentAccount:
        """Hors registre métier. Seul id survit à la projection Pydantic."""
        return await self._request(
            "GET", "/api/v1/auth/me", CurrentAccount, authorization=authorization
        )

    async def _request(
        self,
        method: str,
        path: str,
        response_model: type[R],
        *,
        authorization: str,
        payload: dict[str, JsonValue] | None = None,
        params: dict[str, JsonValue] | None = None,
    ) -> R:
        """Transport privé sans logs, redirections, body d'erreur ni header partagé."""
        require_authorization(authorization)
        error: SpringBootError | None = None
        try:
            response = await self._client.request(
                method, path, headers={"Authorization": authorization},
                json=payload, params=params,
            )
        except httpx.TimeoutException:
            error = SpringTimeoutError()
        except httpx.RequestError:
            error = SpringUnavailableError()
        # Lever hors du except évite de conserver une exception HTTPX contenant
        # request.headers dans __context__. Aucun détail externe n'est propagé.
        if error is not None:
            raise error

        errors = {
            400: SpringValidationError, 422: SpringValidationError,
            401: SpringUnauthorizedError, 403: SpringForbiddenError,
            404: SpringNotFoundError,
        }
        if response.status_code in errors:
            raise errors[response.status_code]()
        if response.status_code >= 500:
            raise SpringUnavailableError()
        if response.status_code != 200:
            raise SpringBootError()

        try:
            result = response_model.model_validate_json(response.content)
        except ValidationError:
            error = SpringResponseError()
        if error is not None:
            raise error
        return result
