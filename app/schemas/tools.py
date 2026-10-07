from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, Field, JsonValue

from app.schemas.spring import (
    ApplicationSearch, OwnerSearch, PageParameters, PositiveId,
    PropertyFilters, PropertySearch, PropertyStatus, StrictRequest,
)


class ToolName(StrEnum):
    SEARCH_MY_PROPERTIES = "search_my_properties"
    GET_PROPERTY_DETAILS = "get_property_details"
    SEARCH_MY_OWNERS = "search_my_owners"
    GET_OWNER_PORTFOLIO = "get_owner_portfolio"
    SEARCH_MY_APPLICATIONS = "search_my_applications"
    GET_APPLICATION_DETAILS = "get_application_details"
    GET_PORTFOLIO_KPIS = "get_portfolio_kpis"
    GET_APPLICATION_KPIS = "get_application_kpis"


# Une entrée par critère ; HTTPX transmet des paramètres sort répétés à Spring.
PropertySort = Annotated[str, Field(pattern=r"^(id|dateCreation|titre|montantLoyer|superficie|statut)(,(asc|desc))?$")]
OwnerSort = Annotated[str, Field(pattern=r"^(id|nom|prenom)(,(asc|desc))?$")]
ApplicationSort = Annotated[str, Field(pattern=r"^(id|dateCandidature|statut)(,(asc|desc))?$")]


class SearchMyPropertiesArguments(PropertySearch, PageParameters):
    sort: list[PropertySort] = Field(default_factory=list)


class GetPropertyDetailsArguments(StrictRequest):
    id: PositiveId


class SearchMyOwnersArguments(OwnerSearch, PageParameters):
    sort: list[OwnerSort] = Field(default_factory=list)


class GetOwnerPortfolioArguments(PropertyFilters, PageParameters):
    id: PositiveId
    status: PropertyStatus | None = None
    sort: list[PropertySort] = Field(default_factory=list)


class SearchMyApplicationsArguments(ApplicationSearch, PageParameters):
    sort: list[ApplicationSort] = Field(default_factory=list)


class GetApplicationDetailsArguments(StrictRequest):
    id: PositiveId


class GetPortfolioKpisArguments(StrictRequest):
    pass


class GetApplicationKpisArguments(PageParameters):
    topLimit: Annotated[int, Field(ge=1, le=20)] = 5


class ToolExecutionRequest(StrictRequest):
    arguments: dict[str, JsonValue]


A = TypeVar("A", bound=BaseModel)
R = TypeVar("R", bound=BaseModel)


@dataclass(frozen=True)
class ToolDefinition(Generic[A, R]):
    name: ToolName
    description: str
    arguments_model: type[A]
    result_model: type[R]
    handler: Callable[[A, str], Awaitable[R]]
