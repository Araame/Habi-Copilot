"""Contrats de ProfessionalDtos.java et PropertyFilterRequest.java.

Les noms JSON Spring sont conservés. Aucun modèle d'entité ni calcul métier.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

PositiveId = Annotated[int, Field(gt=0, le=9223372036854775807)]
NonNegativeInt = Annotated[int, Field(ge=0, le=2147483647)]
ShortText = Annotated[str, Field(max_length=255)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class SpringModel(BaseModel):
    # Projection explicite : tout champ externe non modélisé est écarté.
    model_config = ConfigDict(extra="ignore", strict=True, hide_input_in_errors=True)


class PropertyStatus(StrEnum):
    DRAFT = "DRAFT"
    AVAILABLE = "AVAILABLE"
    RENTED = "RENTED"
    UNAVAILABLE = "UNAVAILABLE"


class ApplicationStatus(StrEnum):
    EN_ATTENTE = "EN_ATTENTE"
    EN_ETUDE = "EN_ETUDE"
    ACCEPTEE = "ACCEPTEE"
    REJETEE = "REJETEE"
    ANNULEE = "ANNULEE"


class Period(StrEnum):
    TODAY = "TODAY"
    THIS_WEEK = "THIS_WEEK"
    THIS_MONTH = "THIS_MONTH"


class PropertyFilters(StrictRequest):
    country: ShortText | None = None
    city: ShortText | None = None
    municipality: ShortText | None = None
    neighborhood: ShortText | None = None
    typeId: PositiveId | None = None
    minRent: NonNegativeInt | None = None
    maxRent: NonNegativeInt | None = None
    rooms: NonNegativeInt | None = None
    bedrooms: NonNegativeInt | None = None
    bathrooms: NonNegativeInt | None = None
    minArea: NonNegativeInt | None = None
    maxArea: NonNegativeInt | None = None
    furnished: bool | None = None
    sharedHousingAllowed: bool | None = None
    minSharedHousingCapacity: Annotated[int, Field(gt=0, le=2147483647)] | None = None
    availableBefore: date | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.minRent is not None and self.maxRent is not None and self.minRent > self.maxRent:
            raise ValueError("minRent doit être inférieur ou égal à maxRent.")
        if self.minArea is not None and self.maxArea is not None and self.minArea > self.maxArea:
            raise ValueError("minArea doit être inférieur ou égal à maxArea.")
        if self.minSharedHousingCapacity is not None and self.sharedHousingAllowed is not True:
            raise ValueError("minSharedHousingCapacity exige sharedHousingAllowed=true.")
        return self


class PageParameters(StrictRequest):
    page: NonNegativeInt = 0
    size: Annotated[int, Field(ge=1, le=100)] = 20

    @model_validator(mode="after")
    def validate_offset(self) -> Self:
        if self.page * self.size > 2147483647:
            raise ValueError("Le décalage de pagination dépasse la limite Spring.")
        return self


class PropertySearch(StrictRequest):
    filters: PropertyFilters | None = None
    status: PropertyStatus | None = None


class OwnerSearch(StrictRequest):
    search: ShortText | None = None


class ApplicationSearch(StrictRequest):
    status: ApplicationStatus | None = None
    propertyId: PositiveId | None = None
    fromDate: date | None = None
    toDate: date | None = None
    period: Period | None = None

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.period is not None and (self.fromDate is not None or self.toDate is not None):
            raise ValueError("Utiliser period ou les dates explicites, pas les deux.")
        if self.fromDate is not None and self.toDate is not None and self.fromDate >= self.toDate:
            raise ValueError("fromDate doit précéder toDate, borne exclusive.")
        return self


class PropertyDetails(SpringModel):
    id: int
    title: str | None
    status: PropertyStatus
    rent: int | None
    deposit: int | None
    typeId: int
    type: str | None
    city: str | None
    municipality: str | None
    neighborhood: str | None
    area: int | None
    rooms: int | None
    bedrooms: int | None
    bathrooms: int | None
    furnished: bool | None
    sharedHousingAllowed: bool | None
    availableFrom: date | None


class OwnerSummary(SpringModel):
    ownerId: int
    displayName: str


class PropertySummary(SpringModel):
    id: int
    title: str | None
    monthlyRent: int | None


class ApplicationInfo(SpringModel):
    id: int
    status: ApplicationStatus
    applicationDate: datetime


class ApplicationSummary(ApplicationInfo):
    property: PropertySummary
    candidateLabel: str


class Candidate(SpringModel):
    profession: str | None
    professionalSituation: str | None
    monthlyIncomeDeclared: int | None


class Documents(SpringModel):
    identityDocumentProvided: bool
    incomeProofProvided: bool


class DossierCompleteness(SpringModel):
    complete: bool
    completionPercentage: int
    missingItems: list[str]


class ApplicationDetails(SpringModel):
    application: ApplicationInfo
    property: PropertySummary
    candidate: Candidate
    documents: Documents
    completeness: DossierCompleteness


class Distribution(SpringModel):
    value: str | None
    count: int


class PortfolioKpis(SpringModel):
    totalProperties: int
    availableProperties: int
    draftProperties: int
    rentedProperties: int
    unavailableProperties: int
    averageRent: float | None
    distributionByType: list[Distribution]
    distributionByCity: list[Distribution]
    distributionByNeighborhood: list[Distribution]


T = TypeVar("T", bound=BaseModel)


class SpringPage(SpringModel, Generic[T]):
    """Projection de PageImpl DIRECT, sans métadonnées internes pageable/sort."""

    content: list[T]
    number: int
    size: int
    totalElements: int
    totalPages: int


class PropertyApplicationCount(SpringModel):
    propertyId: int
    title: str | None
    applicationCount: int


class ApplicationKpis(SpringModel):
    totalApplications: int
    pendingApplications: int
    underReviewApplications: int
    acceptedApplications: int
    rejectedApplications: int
    cancelledApplications: int
    receivedThisWeek: int
    receivedThisMonth: int
    applicationsByProperty: SpringPage[PropertyApplicationCount]
    topPropertiesByApplications: list[PropertyApplicationCount]
    propertiesWithoutApplications: SpringPage[PropertyApplicationCount]


class CurrentAccount(SpringModel):
    """Projection minimale de UserResponse, uniquement pour /auth/me."""

    id: PositiveId
