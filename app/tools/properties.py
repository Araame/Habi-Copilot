from app.clients.spring_client import SpringBootClient
from app.schemas.spring import PropertyDetails, SpringPage
from app.schemas.tools import (
    GetPropertyDetailsArguments, SearchMyPropertiesArguments, ToolDefinition, ToolName,
)


def definitions(client: SpringBootClient) -> tuple[ToolDefinition, ...]:
    return (
        ToolDefinition(ToolName.SEARCH_MY_PROPERTIES, "Rechercher le portefeuille professionnel.",
                       SearchMyPropertiesArguments, SpringPage[PropertyDetails], client.search_my_properties),
        ToolDefinition(ToolName.GET_PROPERTY_DETAILS, "Consulter un bien accessible.",
                       GetPropertyDetailsArguments, PropertyDetails, client.get_property_details),
    )
