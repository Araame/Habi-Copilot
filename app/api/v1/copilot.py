from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.clients.spring_client import require_authorization
from app.core.exceptions import SpringUnauthorizedError
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.spring import (
    ApplicationDetails, ApplicationKpis, ApplicationSummary, OwnerSummary,
    PortfolioKpis, PropertyDetails, SpringPage,
)
from app.schemas.tools import ToolExecutionRequest

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])
development_router = APIRouter(prefix="/api/v1/copilot/tools", tags=["development tools"])
bearer_header = HTTPBearer(
    auto_error=False,
    description="JWT HabiTerra transmis à Spring Boot, qui valide l'identité et les permissions.",
)


async def execution_authorization(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_header)],
) -> str:
    if credentials is None or len(request.headers.getlist("authorization")) != 1:
        raise SpringUnauthorizedError()
    return require_authorization(f"Bearer {credentials.credentials}")


@router.post("/chat", response_model=ChatResponse, responses={
    401: {"model": ChatResponse, "description": "Authentification requise ou expirée"},
    403: {"model": ChatResponse, "description": "Accès refusé par Spring"},
    404: {"model": ChatResponse, "description": "Conversation ou ressource inaccessible"},
    422: {"model": ChatResponse, "description": "Requête invalide"},
    500: {"model": ChatResponse, "description": "Erreur interne"},
    502: {"model": ChatResponse, "description": "Réponse externe invalide"},
    503: {"model": ChatResponse, "description": "Service externe indisponible ou non configuré"},
    504: {"model": ChatResponse, "description": "Délai dépassé"},
})
async def chat(
    body: ChatRequest,
    request: Request,
    authorization: Annotated[str, Depends(execution_authorization)],
) -> JSONResponse:
    response, status_code = await request.app.state.copilot_service.chat(body, authorization=authorization)
    return JSONResponse(
        status_code=status_code, content=response.model_dump(mode="json", by_alias=True),
        headers={"WWW-Authenticate": "Bearer"} if status_code == 401 else None,
    )


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
