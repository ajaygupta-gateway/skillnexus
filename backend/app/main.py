"""
SkillNexus FastAPI Application Entry Point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import settings
from app.core.exceptions import SkillNexusException
from app.core.redis_client import close_redis, get_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown events."""
    # Startup
    print(f"🚀 Starting SkillNexus API [{settings.APP_ENV}]")
    # Warm up Redis connection
    try:
        redis = await get_redis()
        await redis.ping()
        print("✅ Redis connected")
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e}")

    yield

    # Shutdown
    print("🔽 Shutting down SkillNexus API")
    await close_redis()


# ── Application Factory ────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_TITLE,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.APP_DEBUG else None,
        redoc_url="/redoc" if settings.APP_DEBUG else None,
        openapi_url="/openapi.json" if settings.APP_DEBUG else None,
        lifespan=lifespan,
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global Exception Handlers ─────────────────────────────────────────────
    @app.exception_handler(SkillNexusException)
    async def skillnexus_exception_handler(
        request: Request, exc: SkillNexusException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "success": False},
            headers=exc.headers or {},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        if settings.APP_DEBUG:
            import traceback
            detail = f"{type(exc).__name__}: {str(exc)}\n{traceback.format_exc()}"
        else:
            detail = "An internal server error occurred"
        return JSONResponse(
            status_code=500,
            content={"detail": detail, "success": False},
        )

    # ── Routes ─────────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Health Check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    async def health_check():
        return {
            "status": "healthy",
            "app": settings.APP_TITLE,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
        }

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": "Welcome to SkillNexus API",
            "docs": "/docs",
            "version": settings.APP_VERSION,
        }

    return app


app = create_app()
