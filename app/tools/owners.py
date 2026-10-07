from app.clients.spring_client import SpringBootClient
from app.schemas.spring import OwnerSummary, PropertyDetails, SpringPage
from app.schemas.tools import (
    GetOwnerPortfolioArguments, SearchMyOwnersArguments, ToolDefinition, ToolName,
)


def definitions(client: SpringBootClient) -> tuple[ToolDefinition, ...]:
    return (
        ToolDefinition(ToolName.SEARCH_MY_OWNERS, "Rechercher les propriétaires accessibles, sans coordonnées.",
                       SearchMyOwnersArguments, SpringPage[OwnerSummary], client.search_my_owners),
        ToolDefinition(ToolName.GET_OWNER_PORTFOLIO, "Consulter le portefeuille d'un propriétaire autorisé par Spring.",
                       GetOwnerPortfolioArguments, SpringPage[PropertyDetails], client.get_owner_portfolio),
    )
