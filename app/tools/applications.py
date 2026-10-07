from app.clients.spring_client import SpringBootClient
from app.schemas.spring import ApplicationDetails, ApplicationSummary, SpringPage
from app.schemas.tools import (
    GetApplicationDetailsArguments, SearchMyApplicationsArguments, ToolDefinition, ToolName,
)


def definitions(client: SpringBootClient) -> tuple[ToolDefinition, ...]:
    return (
        ToolDefinition(ToolName.SEARCH_MY_APPLICATIONS, "Rechercher les candidatures accessibles.",
                       SearchMyApplicationsArguments, SpringPage[ApplicationSummary], client.search_my_applications),
        ToolDefinition(ToolName.GET_APPLICATION_DETAILS, "Lire une candidature ; revenu déclaré et présence de justificatifs uniquement.",
                       GetApplicationDetailsArguments, ApplicationDetails, client.get_application_details),
    )
