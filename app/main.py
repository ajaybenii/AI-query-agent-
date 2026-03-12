"""
app/main.py
────────────
FastAPI application factory.

Middleware stack (outermost → innermost):
  1. CORS
  2. Request ID injection
  3. Request/Response logging
  4. Exception handler normalisation
"""

import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.routes.query import router as query_router
from app.config import get_settings
from app.database.connection import connect_db, disconnect_db
from app.utils.logger import setup_logger


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logger()

    app = FastAPI(
        title="AI Query Agent — ERP Chatbot",
        description=(
            "GenAI-powered agent that converts natural language questions "
            "into MongoDB queries and returns human-friendly answers."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request ID & Logging Middleware ────────────────────────────────────────
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        t_start = time.perf_counter()
        logger.info(
            f"→ {request.method} {request.url.path} "
            f"| client={request.client.host if request.client else 'unknown'} "
            f"| id={request_id}"
        )

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        logger.info(
            f"← {request.method} {request.url.path} "
            f"| status={response.status_code} "
            f"| {elapsed_ms:.1f}ms "
            f"| id={request_id}"
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"
        return response

    # ── Global Exception Handler ───────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception(f"Unhandled exception [{request_id}]: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "detail": str(exc) if not settings.is_production else "An unexpected error occurred.",
                "request_id": request_id,
            },
        )

    # ── Startup / Shutdown ─────────────────────────────────────────────────────
    @app.on_event("startup")
    async def startup():
        logger.info("Starting AI Query Agent ...")
        await connect_db()
        logger.info("AI Query Agent ready ✓")

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("Shutting down AI Query Agent ...")
        await disconnect_db()

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(query_router)

    # ── Root redirect ──────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": "AI Query Agent is running. Visit /docs for the API reference."}

    return app


app = create_app()
