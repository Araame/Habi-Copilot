from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.copilot import development_router, router
from app.clients.spring_client import SpringBootClient
from app.clients.llm_client import GroqLLMClient
from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidToolArgumentsError, SpringBootError, UnknownToolError
from app.memory.store import InMemoryConversationStore
from app.schemas.chat import ChatResponse
from app.services.conversation_service import ConversationService, SpringAuthenticatedPrincipalResolver
from app.services.copilot_service import CopilotService
from app.services.planner import PlannerService
from app.services.property_type_resolver import PropertyTypeResolver
from app.services.response_service import ResponseService
from app.tools.registry import ToolRegistry


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Un logger dédié, sans activation des logs détaillés HTTPX/Groq.
    logger = logging.getLogger("habi.copilot")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    settings = application.state.settings
    spring_client = SpringBootClient(settings)
    application.state.spring_client = spring_client
    application.state.conversation_store = InMemoryConversationStore(
        ttl_minutes=settings.copilot_conversation_ttl_minutes
    )
    application.state.tool_registry = ToolRegistry(spring_client)
    application.state.principal_resolver = SpringAuthenticatedPrincipalResolver(spring_client)
    llm = GroqLLMClient(settings)
    application.state.llm_client = llm
    application.state.copilot_service = CopilotService(
        principal=application.state.principal_resolver,
        conversations=ConversationService(application.state.conversation_store),
        planner=PlannerService(llm, application.state.tool_registry),
        registry=application.state.tool_registry,
        types=PropertyTypeResolver(spring_client),
        responses=ResponseService(), settings=settings,
    )
    try:
        yield
    finally:
        try:
            await llm.aclose()
        finally:
            await spring_client.aclose()


async def health() -> dict[str, str]:
    return {"status": "ok", "service": "habi-agency-copilot"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    application = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
    application.state.settings = settings
    application.include_router(router)
    if settings.app_env == "development":
        application.include_router(development_router)
    application.add_api_route("/health", health, methods=["GET"], tags=["health"])

    @application.exception_handler(SpringBootError)
    async def spring_error_handler(request: Request, exc: SpringBootError) -> JSONResponse:
        content = {"code": exc.code, "message": exc.message}
        if request.url.path == "/api/v1/copilot/chat":
            content = ChatResponse(status="ERROR", answer=exc.message, error_code=exc.code).model_dump(mode="json", by_alias=True)
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
        )

    @application.exception_handler(UnknownToolError)
    async def unknown_tool_handler(request: Request, exc: UnknownToolError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": "UNKNOWN_TOOL", "message": "Outil inconnu."})

    @application.exception_handler(InvalidToolArgumentsError)
    @application.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: Exception) -> JSONResponse:
        # Ne pas sérialiser exc.errors() : input peut contenir des données sensibles.
        content = {"code": "INVALID_ARGUMENTS", "message": "Corps ou arguments invalides."}
        if request.url.path == "/api/v1/copilot/chat":
            content = ChatResponse(status="ERROR", answer=content["message"], error_code=content["code"]).model_dump(mode="json", by_alias=True)
        return JSONResponse(status_code=422, content=content)

    return application


app = create_app()
