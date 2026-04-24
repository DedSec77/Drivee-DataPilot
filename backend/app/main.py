from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import (
    admin,
    ask,
    datasource,
    dictionary,
    execute,
    schedule,
    summarize,
    templates,
)
from app.api import (
    eval as eval_api,
)
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.scheduler import SCHEDULED_DIR, start_scheduler, stop_scheduler


def _setup_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level=settings.log_level, serialize=False)


def _prewarm_llm() -> None:
    try:
        from app.core.llm import get_llm

        llm = get_llm()
        _ = llm.primary.complete("ping", "Ответь одним словом: OK.", temperature=0.0)
        logger.info("[prewarm] llama.cpp is ready")
    except Exception as e:
        logger.warning(f"[prewarm] skipped ({e})")


def _prewarm_value_links() -> None:
    try:
        from app.core.value_linker import get_value_linker

        linker = get_value_linker()
        n = linker.index()
        logger.info(f"[prewarm] value linker indexed {n} value(s) {linker.stats}")
    except Exception as e:
        logger.warning(f"[prewarm] value linker skipped ({e})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    logger.info(f"Drivee DataPilot starting (env={settings.environment})")
    start_scheduler()
    _prewarm_llm()
    _prewarm_value_links()
    yield
    stop_scheduler()
    logger.info("Drivee DataPilot stopped")


IS_PROD = settings.is_prod

app = FastAPI(
    title="Drivee DataPilot",
    version="0.1.0",
    description="Self-service NL→SQL аналитика для Drivee",
    lifespan=lifespan,
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if IS_PROD:
    _allowed_origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
    if not _allowed_origins or "*" in _allowed_origins:
        raise RuntimeError(
            "FRONTEND_ORIGIN must be a non-wildcard list in production "
            "(comma-separated). '*' would let any site call /api with "
            "the user's token."
        )
    if not settings.api_token:
        raise RuntimeError("API_TOKEN must be set in production - the API otherwise serves unauthenticated.")
    _allowed_methods = ["GET", "POST", "DELETE", "OPTIONS"]
else:
    _allowed_origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()] or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    _allowed_methods = ["GET", "POST", "DELETE", "OPTIONS"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=_allowed_methods,
    allow_headers=["Content-Type", "X-API-Token"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if IS_PROD:
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'",
        )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            {"detail": exc.errors()},
            custom_encoder={Exception: lambda e: str(e)},
        ),
    )


app.include_router(ask.router, prefix="/api", tags=["ask"])
app.include_router(execute.router, prefix="/api", tags=["execute"])
app.include_router(templates.router, prefix="/api", tags=["templates"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])
app.include_router(eval_api.router, prefix="/api", tags=["eval"])
app.include_router(dictionary.router, prefix="/api", tags=["dictionary"])
app.include_router(datasource.router, prefix="/api", tags=["datasource"])
app.include_router(summarize.router, prefix="/api", tags=["summarize"])
app.include_router(admin.router, prefix="/api", tags=["admin"])

SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/files/scheduled", StaticFiles(directory=str(SCHEDULED_DIR)), name="scheduled-files")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.environment}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "drivee-datapilot", "docs": "/docs" if not IS_PROD else "disabled"}
