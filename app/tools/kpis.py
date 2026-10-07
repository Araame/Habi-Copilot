from app.clients.spring_client import SpringBootClient
from app.schemas.spring import ApplicationKpis, PortfolioKpis
from app.schemas.tools import (
    GetApplicationKpisArguments, GetPortfolioKpisArguments, ToolDefinition, ToolName,
)


def definitions(client: SpringBootClient) -> tuple[ToolDefinition, ...]:
    return (
        ToolDefinition(ToolName.GET_PORTFOLIO_KPIS, "Lire les KPI du portefeuille calculés par Spring Boot.",
                       GetPortfolioKpisArguments, PortfolioKpis, client.get_portfolio_kpis),
        ToolDefinition(ToolName.GET_APPLICATION_KPIS, "Lire les KPI des candidatures calculés par Spring Boot.",
                       GetApplicationKpisArguments, ApplicationKpis, client.get_application_kpis),
    )
