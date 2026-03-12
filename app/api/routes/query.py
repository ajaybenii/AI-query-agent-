"""
app/api/routes/query.py
────────────────────────
Query Agent API endpoints.

POST /api/v1/query      → Main NL-to-MongoDB chatbot endpoint
GET  /api/v1/health     → Health check
GET  /api/v1/examples   → Sample questions with expected intent
"""

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.database.connection import get_database
from app.models.schemas import (
    ErrorResponse,
    GeneratedQuery,
    HealthResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.llm_service import LLMService, get_llm_service
from app.services.query_executor import QueryExecutionError, QueryExecutor
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Query Agent"])


# ── Dependencies ──────────────────────────────────────────────────────────────

def get_executor(request: Request) -> QueryExecutor:
    db = get_database()
    return QueryExecutor(db)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Natural Language Query",
    description=(
        "Submit a natural language question about the ERP system. "
        "The agent will generate a MongoDB query, execute it, and return a human-friendly answer."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid question"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "LLM or Database unavailable"},
    },
)
async def execute_query(
    payload: QueryRequest,
    request: Request,
    llm: LLMService = Depends(get_llm_service),
    executor: QueryExecutor = Depends(get_executor),
) -> QueryResponse:
    request_id = str(uuid.uuid4())
    t_start = time.perf_counter()

    logger.info(f"[{request_id}] Question: {payload.question!r}")

    try:
        # Step 1: NL → MongoDB query (via LLM)
        generated_query: GeneratedQuery = await llm.generate_query(
            question=payload.question,
            max_results=payload.max_results,
        )
        logger.debug(
            f"[{request_id}] Generated: op={generated_query.operation} "
            f"collection={generated_query.collection}"
        )

        # Step 2: Execute query against MongoDB
        results = await executor.execute(generated_query, max_results=payload.max_results)

        # Step 3: Format results into natural language answer
        answer = await llm.format_answer(
            question=payload.question,
            results=results,
            query=generated_query,
        )

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        logger.info(
            f"[{request_id}] Completed in {elapsed_ms:.1f}ms | "
            f"{len(results)} result(s)"
        )

        return QueryResponse(
            question=payload.question,
            answer=answer,
            query=generated_query,
            results=results,
            total_results=len(results),
            execution_time_ms=round(elapsed_ms, 2),
        )

    except QueryExecutionError as exc:
        logger.warning(f"[{request_id}] Query execution error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Query execution failed", "detail": str(exc), "request_id": request_id},
        )
    except ValueError as exc:
        logger.warning(f"[{request_id}] Validation error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid input", "detail": str(exc), "request_id": request_id},
        )
    except Exception as exc:
        logger.exception(f"[{request_id}] Unexpected error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Internal server error", "detail": str(exc), "request_id": request_id},
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
)
async def health_check(request: Request) -> HealthResponse:
    from app.config import get_settings
    settings = get_settings()

    # Check MongoDB
    mongo_status = "unknown"
    try:
        db = get_database()
        await db.command("ping")
        mongo_status = "connected"
    except Exception as exc:
        mongo_status = f"error: {exc}"

    return HealthResponse(
        status="ok" if mongo_status == "connected" else "degraded",
        mongodb=mongo_status,
        llm_provider=settings.llm_provider,
    )


@router.get(
    "/examples",
    summary="Example Questions",
    description="Returns sample NL questions grouped by complexity level.",
)
async def get_examples() -> dict[str, Any]:
    return {
        "examples": {
            "level_1_basic": [
                "List all students in class 6",
                "Show the attendance of student with roll number 3 for today",
                "List all teachers in the system",
                "Show all assignments created today",
            ],
            "level_2_filtering": [
                "Show students who were absent yesterday",
                "List assignments due this week",
                "Show students belonging to section A of class 6",
                "Show all exams scheduled this month",
            ],
            "level_3_aggregation": [
                "Count how many students were absent today",
                "Show the number of assignments submitted per class",
                "Find the class with the highest number of absent students today",
            ],
            "level_4_multi_collection": [
                "Show students who have not submitted any assignment",
                "List teachers and the classes they teach",
                "Show attendance percentage of each student",
            ],
            "level_5_analytical": [
                "Show the top 5 students with the highest attendance percentage",
            ],
        }
    }
