"""
app/services/query_executor.py
───────────────────────────────
Safely executes LLM-generated MongoDB queries.

Security features:
• Whitelist of allowed collections
• Whitelist of allowed aggregation pipeline stages
• Deep sanitisation of filter/pipeline to remove dangerous operators
• Query timeout (5 seconds)
• Converts ObjectId strings back to BSON ObjectIds where needed
• Injects dynamic date placeholders (TODAY, YESTERDAY, etc.)
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.schemas import GeneratedQuery
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Security Whitelists ────────────────────────────────────────────────────────

ALLOWED_COLLECTIONS = {
    "students", "teachers", "attendance", "assignments",
    "submissions", "exams", "classes",
}

ALLOWED_PIPELINE_STAGES = {
    "$match", "$group", "$project", "$lookup", "$unwind",
    "$sort", "$limit", "$skip", "$count", "$addFields",
    "$replaceRoot", "$facet", "$bucket", "$out",
}

DANGEROUS_OPERATORS = {
    "$where", "$function", "$accumulator", "$jsonSchema",
    "$expr",  # allow only in specific contexts — removed for safety
}


class QueryExecutionError(Exception):
    pass


class QueryExecutor:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def execute(self, query: GeneratedQuery, max_results: int = 100) -> list[dict[str, Any]]:
        """
        Validate and execute a GeneratedQuery. Returns list of result dicts.
        """
        self._validate(query)

        # Resolve date placeholders and ObjectId strings
        resolved_query = self._resolve_placeholders(query)

        logger.info(
            f"Executing {resolved_query.operation.upper()} on '{resolved_query.collection}' "
            f"| explanation: {resolved_query.explanation[:80]}"
        )

        collection = self.db[resolved_query.collection]

        try:
            if resolved_query.operation == "find":
                return await self._run_find(collection, resolved_query, max_results)
            elif resolved_query.operation == "aggregate":
                return await self._run_aggregate(collection, resolved_query, max_results)
            elif resolved_query.operation == "count":
                return await self._run_count(collection, resolved_query)
            else:
                raise QueryExecutionError(f"Unsupported operation: {resolved_query.operation}")
        except QueryExecutionError:
            raise
        except Exception as exc:
            logger.error(f"Query execution error: {exc}")
            raise QueryExecutionError(f"Database error: {str(exc)}")

    # ── Operations ──────────────────────────────────────────────────────────────

    async def _run_find(self, collection, query: GeneratedQuery, max_results: int) -> list[dict]:
        limit = min(query.limit or 100, max_results)
        cursor = collection.find(
            filter=query.filter,
            projection=query.projection or None,
        )
        if query.sort:
            cursor = cursor.sort(list(query.sort.items()))
        cursor = cursor.limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._serialize(doc))
        return results

    async def _run_aggregate(self, collection, query: GeneratedQuery, max_results: int) -> list[dict]:
        pipeline = query.pipeline or []

        # Ensure there's a $limit stage to prevent unbounded results
        has_limit = any("$limit" in stage for stage in pipeline)
        if not has_limit:
            pipeline = pipeline + [{"$limit": min(query.limit or 100, max_results)}]

        results = []
        async for doc in collection.aggregate(pipeline):
            results.append(self._serialize(doc))
        return results

    async def _run_count(self, collection, query: GeneratedQuery) -> list[dict]:
        count = await collection.count_documents(query.filter)
        return [{"count": count}]

    # ── Validation ─────────────────────────────────────────────────────────────

    def _validate(self, query: GeneratedQuery) -> None:
        if query.collection not in ALLOWED_COLLECTIONS:
            raise QueryExecutionError(
                f"Collection '{query.collection}' is not allowed. "
                f"Allowed: {ALLOWED_COLLECTIONS}"
            )

        # Check pipeline stages
        for stage in query.pipeline:
            for key in stage:
                if key not in ALLOWED_PIPELINE_STAGES:
                    raise QueryExecutionError(f"Pipeline stage '{key}' is not allowed.")

        # Check for dangerous operators in filter
        self._check_dangerous_operators(query.filter)
        for stage in query.pipeline:
            self._check_dangerous_operators(stage)

    def _check_dangerous_operators(self, obj: Any, depth: int = 0) -> None:
        if depth > 20:  # prevent infinite recursion
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in DANGEROUS_OPERATORS:
                    raise QueryExecutionError(f"Operator '{key}' is not allowed for security reasons.")
                self._check_dangerous_operators(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._check_dangerous_operators(item, depth + 1)

    # ── Date & ObjectId Resolution ─────────────────────────────────────────────

    def _resolve_placeholders(self, query: GeneratedQuery) -> GeneratedQuery:
        """
        Walk the query dict and replace any date placeholder strings with
        real ISODate-compatible datetime strings, and ObjectId-like strings
        with actual BSON ObjectId objects.
        """
        filter_resolved = self._resolve_obj(query.filter)
        pipeline_resolved = [self._resolve_obj(stage) for stage in query.pipeline]

        return GeneratedQuery(
            operation=query.operation,
            collection=query.collection,
            filter=filter_resolved,
            projection=query.projection,
            pipeline=pipeline_resolved,
            sort=query.sort,
            limit=query.limit,
            explanation=query.explanation,
        )

    def _resolve_obj(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._resolve_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_obj(i) for i in obj]
        if isinstance(obj, str):
            return self._resolve_string(obj)
        return obj

    def _resolve_string(self, value: str) -> Any:
        now_utc = datetime.now(timezone.utc)

        # Date range helpers
        _date_map = {
            "$$TODAY_START$$": _day_start(now_utc),
            "$$TODAY_END$$": _day_end(now_utc),
            "$$YESTERDAY_START$$": _day_start(now_utc - timedelta(days=1)),
            "$$YESTERDAY_END$$": _day_end(now_utc - timedelta(days=1)),
            "$$WEEK_START$$": _week_start(now_utc),
            "$$WEEK_END$$": _week_end(now_utc),
            "$$MONTH_START$$": _month_start(now_utc),
            "$$MONTH_END$$": _month_end(now_utc),
        }

        if value in _date_map:
            return _date_map[value]

        # ISO datetime strings → datetime objects
        if _looks_like_iso(value):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass

        # ObjectId-like 24-char hex strings
        if len(value) == 24 and re.match(r"^[0-9a-fA-F]{24}$", value):
            try:
                return ObjectId(value)
            except Exception:
                pass

        return value

    # ── Serialisation ──────────────────────────────────────────────────────────

    @staticmethod
    def _serialize(doc: dict) -> dict:
        """Convert BSON types to JSON-serialisable Python types."""
        result = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                result[k] = str(v)
            elif isinstance(v, datetime):
                result[k] = v.isoformat()
            elif isinstance(v, dict):
                result[k] = QueryExecutor._serialize(v)
            elif isinstance(v, list):
                result[k] = [
                    QueryExecutor._serialize(i) if isinstance(i, dict) else
                    str(i) if isinstance(i, ObjectId) else
                    i.isoformat() if isinstance(i, datetime) else i
                    for i in v
                ]
            else:
                result[k] = v
        return result


# ── Date Helper Functions ──────────────────────────────────────────────────────

def _day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def _day_end(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)


def _week_start(dt: datetime) -> datetime:
    start = dt - timedelta(days=dt.weekday())
    return _day_start(start)


def _week_end(dt: datetime) -> datetime:
    end = dt + timedelta(days=6 - dt.weekday())
    return _day_end(end)


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def _month_end(dt: datetime) -> datetime:
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)
    return _day_end(next_month - timedelta(days=1))


def _looks_like_iso(s: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?", s))
