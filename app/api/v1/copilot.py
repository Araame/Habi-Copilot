from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.clients.spring_client import require_authorization
from app.core.exceptions import CopilotNotImplementedError, SpringUnauthorizedError
from app.schemas.chat import ChatRequest, NotImplementedResponse
from app.schemas.spring import (
    ApplicationDetails, ApplicationKpis, ApplicationSummary, OwnerSummary,
    PortfolioKpis, PropertyDetails, SpringPage,
)
from app.schemas.tools import ToolExecutionRequest
from app.services.copilot_service import CopilotService

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])
development_router = APIRouter(prefix="/api/v1/copilot/tools", tags=["development tools"])
bearer_header = HTTPBearer(
    auto_error=False,
    description="JWT HabiTerra transmis à Spring Boot, qui valide l'identité et les permissions.",
)


@router.post("/chat", status_code=501, response_model=NotImplementedResponse)
async def chat(
    request: ChatRequest,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_header)],
) -> JSONResponse:
    # Le header est documenté, sans validation du JWT ni accès à des données.
    # Ne jamais logger credentials ni le transmettre au LLM.
    try:
        await CopilotService().chat(request)
    except CopilotNotImplementedError:
        return JSONResponse(status_code=501, content=NotImplementedResponse().model_dump())
    raise RuntimeError("Le contrat du chat doit être implémenté avant activation.")


async def execution_authorization(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_header)],
) -> str:
    if credentials is None or len(request.headers.getlist("authorization")) != 1:
        raise SpringUnauthorizedError()
    return require_authorization(f"Bearer {credentials.credentials}")


@development_router.post(
    "/{tool_name}/execute",
    response_model=(
        SpringPage[PropertyDetails] | PropertyDetails | SpringPage[OwnerSummary]
        | SpringPage[ApplicationSummary] | ApplicationDetails | PortfolioKpis | ApplicationKpis
    ),
    description="Développement uniquement. Arguments stricts par outil : voir README. Aucun LLM.",
    responses={
        401: {"description": "Authorization absent, mal formé ou refusé par Spring"},
        403: {"description": "Accès refusé par Spring"},
        404: {"description": "Outil inconnu ou ressource inaccessible"},
        422: {"description": "Arguments invalides"},
        502: {"description": "Réponse Spring invalide"},
        503: {"description": "Spring indisponible"},
        504: {"description": "Timeout Spring"},
    },
)
async def execute_tool(
    tool_name: str,
    body: ToolExecutionRequest,
    request: Request,
    authorization: Annotated[str, Depends(execution_authorization)],
) -> JSONResponse:
    result = await request.app.state.tool_registry.execute_tool(
        tool_name, body.arguments, authorization
    )
    return JSONResponse(content=result.model_dump(mode="json"))
