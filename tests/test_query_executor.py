"""
tests/test_query_executor.py
─────────────────────────────
Unit tests for the query executor (sanitisation, date resolution, etc.)
Run: pytest tests/ -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.schemas import GeneratedQuery
from app.services.query_executor import (
    QueryExecutionError,
    QueryExecutor,
    _day_start,
    _day_end,
    _week_start,
    _month_start,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_executor():
    mock_db = MagicMock()
    return QueryExecutor(mock_db)


def make_query(**kwargs) -> GeneratedQuery:
    defaults = {
        "operation": "find",
        "collection": "students",
        "filter": {},
        "projection": {},
        "pipeline": [],
        "sort": {},
        "limit": 10,
        "explanation": "test",
    }
    defaults.update(kwargs)
    return GeneratedQuery(**defaults)


# ── Validation Tests ──────────────────────────────────────────────────────────

class TestValidation:
    def test_invalid_collection_raises(self):
        executor = make_executor()
        q = make_query(collection="secret_data")
        with pytest.raises(QueryExecutionError, match="not allowed"):
            executor._validate(q)

    def test_valid_collection_passes(self):
        executor = make_executor()
        for col in ["students", "teachers", "attendance", "assignments", "submissions", "exams", "classes"]:
            q = make_query(collection=col)
            executor._validate(q)  # should not raise

    def test_dangerous_operator_in_filter_raises(self):
        executor = make_executor()
        q = make_query(filter={"$where": "function() { return true; }"})
        with pytest.raises(QueryExecutionError, match="not allowed"):
            executor._validate(q)

    def test_dangerous_operator_nested_raises(self):
        executor = make_executor()
        q = make_query(filter={"name": {"$where": "..."}})
        with pytest.raises(QueryExecutionError, match="not allowed"):
            executor._validate(q)

    def test_invalid_pipeline_stage_raises(self):
        executor = make_executor()
        q = make_query(
            operation="aggregate",
            pipeline=[{"$hack": {}}],
        )
        with pytest.raises(QueryExecutionError, match="not allowed"):
            executor._validate(q)

    def test_valid_pipeline_stages_pass(self):
        executor = make_executor()
        q = make_query(
            operation="aggregate",
            pipeline=[
                {"$match": {"class": "6"}},
                {"$group": {"_id": "$section", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
        )
        executor._validate(q)  # should not raise


# ── Date Resolution Tests ─────────────────────────────────────────────────────

class TestDateResolution:
    def test_iso_string_converted_to_datetime(self):
        executor = make_executor()
        result = executor._resolve_string("2024-01-15T00:00:00+00:00")
        assert isinstance(result, datetime)

    def test_non_date_string_unchanged(self):
        executor = make_executor()
        result = executor._resolve_string("hello world")
        assert result == "hello world"

    def test_filter_with_iso_dates_resolved(self):
        executor = make_executor()
        q = make_query(filter={"date": {"$gte": "2024-01-01T00:00:00Z"}})
        resolved = executor._resolve_placeholders(q)
        assert isinstance(resolved.filter["date"]["$gte"], datetime)


# ── Serialisation Tests ────────────────────────────────────────────────────────

class TestSerialisation:
    def test_objectid_serialised_to_string(self):
        from bson import ObjectId
        doc = {"_id": ObjectId("507f1f77bcf86cd799439011"), "name": "Test"}
        result = QueryExecutor._serialize(doc)
        assert isinstance(result["_id"], str)
        assert result["_id"] == "507f1f77bcf86cd799439011"

    def test_datetime_serialised_to_isoformat(self):
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        doc = {"date": dt, "name": "Test"}
        result = QueryExecutor._serialize(doc)
        assert isinstance(result["date"], str)
        assert "2024-01-15" in result["date"]

    def test_nested_dict_serialised(self):
        from bson import ObjectId
        doc = {"nested": {"_id": ObjectId("507f1f77bcf86cd799439011")}}
        result = QueryExecutor._serialize(doc)
        assert isinstance(result["nested"]["_id"], str)


# ── Date Helper Tests ─────────────────────────────────────────────────────────

class TestDateHelpers:
    def test_day_start_zeroes_time(self):
        dt = datetime(2024, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = _day_start(dt)
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0

    def test_day_end_maxes_time(self):
        dt = datetime(2024, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = _day_end(dt)
        assert result.hour == 23
        assert result.minute == 59
        assert result.second == 59

    def test_week_start_is_monday(self):
        # June 15, 2024 is a Saturday
        dt = datetime(2024, 6, 15, tzinfo=timezone.utc)
        result = _week_start(dt)
        assert result.weekday() == 0  # Monday
        assert result.day == 10  # June 10

    def test_month_start_is_first_day(self):
        dt = datetime(2024, 6, 15, tzinfo=timezone.utc)
        result = _month_start(dt)
        assert result.day == 1
        assert result.month == 6
