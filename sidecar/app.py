from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from sidecar import session
from sidecar.services.bus import get_event_bus

TOKEN_HEADER = "X-PhantomX-Token"

PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
        "/openapi.json",
    }
)

ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
]


def extract_token(request: Request) -> str:
    """
    Pull the session token from the header, a Bearer header, or the query string.
    The query string exists because EventSource cannot send custom headers.
    """
    token = request.headers.get(TOKEN_HEADER)
    if token:
        return token

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]

    return request.query_params.get("token", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bind the EventBus to this loop so worker threads can emit before any
    # SSE client has subscribed.
    get_event_bus().bind_loop(asyncio.get_running_loop())
    logger.info("Sidecar app ready")
    yield
    logger.info("Sidecar app shutting down")


def create_app() -> FastAPI:
    """
    FastAPI factory called by Uvicorn.
    """
    app = FastAPI(
        title="PhantomX Sidecar",
        version="2.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )

    # Registered FIRST so it ends up INSIDE CORSMiddleware: Starlette treats the
    # most recently added middleware as the outermost one. CORS must own the
    # preflight, otherwise OPTIONS (which carries no token) is rejected.
    @app.middleware("http")
    async def verify_token(request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Never log Ely.by login payloads (password / 2FA).
        if request.url.path == "/api/auth/elyby/login":
            logger.debug(f"Ely.by login attempt from {request.client.host if request.client else 'unknown'}")

        expected = session.get_token()
        provided = extract_token(request)

        if not expected or not secrets.compare_digest(provided, expected):
            client = request.client.host if request.client else "unknown"
            logger.warning(f"Unauthorized {request.method} {request.url.path} from {client}")
            # Returned, never raised: an HTTPException raised here would bypass
            # Starlette's ExceptionMiddleware and surface as a 500.
            return JSONResponse(
                status_code=403,
                content={"detail": f"Invalid or missing {TOKEN_HEADER}"},
            )

        return await call_next(request)

    # Registered LAST so it is the outermost middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    from sidecar.api import auth, events, instances, java, marketplace, minecraft, modpack, mods, repair, settings, supporter, system_diagnostics, tasks

    app.include_router(events.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api/tasks")
    app.include_router(minecraft.router, prefix="/api/minecraft")
    app.include_router(instances.router, prefix="/api/instances")
    app.include_router(mods.router, prefix="/api/instances")
    app.include_router(settings.router, prefix="/api/settings")
    app.include_router(java.router, prefix="/api/system/java")
    app.include_router(marketplace.router, prefix="/api/marketplace")
    app.include_router(modpack.router, prefix="/api/marketplace/modpack")
    app.include_router(system_diagnostics.router, prefix="/api/system")
    app.include_router(repair.router, prefix="/api/repair")
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(supporter.router, prefix="/api/supporter")


    logger.info("FastAPI app created")
    return app
