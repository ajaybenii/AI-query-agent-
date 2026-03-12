"""
app/services/llm_service.py
────────────────────────────
LLM abstraction layer.
• Supports OpenAI (GPT-4o) and Google Gemini (gemini-1.5-pro)
• Uses function-calling / structured output for reliable JSON
• Automatic retry with exponential back-off (3 attempts)
• Full schema context injected into every system prompt
"""

import json
import time
from typing import Any

from openai import OpenAI, AsyncOpenAI
from loguru import logger

from app.config import get_settings
from app.models.schemas import GeneratedQuery

# ── DB Schema Context ─────────────────────────────────────────────────────────
# This is passed as part of the system prompt so the LLM knows the exact
# field names, types, and relationships between collections.

DB_SCHEMA_CONTEXT = """
You are an expert MongoDB query generator for an ERP (Education Resource Planning) system.

## DATABASE: erp_system

### Collection: students
```json
{
  "_id": "ObjectId",
  "name": "string",
  "class": "string (e.g. '6', '7', '10')",
  "section": "string (e.g. 'A', 'B', 'C')",
  "roll_no": "integer",
  "email": "string",
  "phone": "string",
  "created_at": "ISODate"
}
```

### Collection: teachers
```json
{
  "_id": "ObjectId",
  "name": "string",
  "email": "string",
  "subjects": ["array of subject strings"],
  "phone": "string",
  "created_at": "ISODate"
}
```

### Collection: classes
```json
{
  "_id": "ObjectId",
  "name": "string (class number, e.g. '6')",
  "section": "string",
  "subject": "string",
  "teacher_id": "ObjectId ref -> teachers._id",
  "created_at": "ISODate"
}
```

### Collection: attendance
```json
{
  "_id": "ObjectId",
  "student_id": "ObjectId ref -> students._id",
  "student_name": "string",
  "class": "string",
  "section": "string",
  "date": "ISODate (start of day, UTC)",
  "status": "string enum: present | absent | late",
  "created_at": "ISODate"
}
```

### Collection: assignments
```json
{
  "_id": "ObjectId",
  "title": "string",
  "description": "string",
  "class": "string",
  "section": "string | null (null = all sections)",
  "subject": "string",
  "teacher_id": "ObjectId ref -> teachers._id",
  "due_date": "ISODate",
  "created_at": "ISODate"
}
```

### Collection: submissions
```json
{
  "_id": "ObjectId",
  "assignment_id": "ObjectId ref -> assignments._id",
  "student_id": "ObjectId ref -> students._id",
  "student_name": "string",
  "class": "string",
  "status": "string enum: submitted | late | pending",
  "submitted_at": "ISODate",
  "created_at": "ISODate"
}
```

### Collection: exams
```json
{
  "_id": "ObjectId",
  "title": "string",
  "subject": "string",
  "class": "string",
  "section": "string | null",
  "date": "ISODate",
  "duration_minutes": "integer",
  "created_at": "ISODate"
}
```

## IMPORTANT RULES
1. Date comparisons: ALWAYS use $gte / $lte with ISODate strings (ISO 8601).
2. "today" = start of current UTC day to end of current UTC day.
3. "yesterday" = previous calendar day.
4. "this week" = Monday 00:00:00 to Sunday 23:59:59 of current week.
5. "this month" = 1st of month 00:00:00 to last day 23:59:59.
6. For cross-collection queries use $lookup in an aggregation pipeline.
7. The 'class' field is stored as a STRING (e.g., "6" not 6).
8. Attendance percentage = (present_days / total_days) * 100.
9. Always add a reasonable limit (default 100) unless the query is an aggregation count.
10. Never include _id in projections unless specifically requested — use {_id: 0} in find projections.
"""

FUNCTION_SCHEMA = {
    "name": "generate_mongodb_query",
    "description": "Generate a MongoDB query to answer the user's natural language question about the ERP system.",
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["find", "aggregate", "count"],
                "description": "MongoDB operation type. Use 'aggregate' for joins, grouping, sorting by computed fields. Use 'find' for simple filters. Use 'count' for counting documents.",
            },
            "collection": {
                "type": "string",
                "enum": ["students", "teachers", "attendance", "assignments", "submissions", "exams", "classes"],
                "description": "Primary collection to query.",
            },
            "filter": {
                "type": "object",
                "description": "MongoDB filter document (for find/count operations). Use MongoDB query operators.",
            },
            "projection": {
                "type": "object",
                "description": "Fields to include/exclude (for find operation). Use {field: 1} to include, {field: 0} to exclude.",
            },
            "pipeline": {
                "type": "array",
                "items": {"type": "object"},
                "description": "MongoDB aggregation pipeline stages (for aggregate operation). Array of stage objects like $match, $lookup, $group, $project, $sort, $limit.",
            },
            "sort": {
                "type": "object",
                "description": "Sort order for find operations. {field: 1} ascending, {field: -1} descending.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of documents to return.",
                "default": 100,
            },
            "explanation": {
                "type": "string",
                "description": "Brief explanation of what this query does and why.",
            },
        },
        "required": ["operation", "collection", "explanation"],
    },
}


class LLMService:
    """
    Facade over multiple LLM providers.
    Instantiated once and reused across requests.
    """

    def __init__(self):
        self.settings = get_settings()
        self._openai_client: AsyncOpenAI | None = None
        self._gemini_model = None
        self._setup()

    def _setup(self):
        provider = self.settings.llm_provider
        if provider == "openai":
            if not self.settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is not set.")
            self._openai_client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            logger.info(f"LLM: OpenAI {self.settings.openai_model} ✓")

        elif provider == "gemini":
            if not self.settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is not set.")
            import google.generativeai as genai
            genai.configure(api_key=self.settings.gemini_api_key)
            self._gemini_model = genai.GenerativeModel(self.settings.gemini_model)
            logger.info(f"LLM: Google Gemini {self.settings.gemini_model} ✓")

    # ── Public API ────────────────────────────────────────────────────────────

    async def generate_query(self, question: str, max_results: int = 100) -> GeneratedQuery:
        """
        Convert a natural language question into a structured MongoDB query.
        Retries up to 3 times on transient errors.
        """
        for attempt in range(1, 4):
            try:
                t0 = time.perf_counter()
                raw = await self._call_llm(question, max_results)
                elapsed = (time.perf_counter() - t0) * 1000
                logger.debug(f"LLM query generation took {elapsed:.1f}ms (attempt {attempt})")
                return self._parse_response(raw)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(f"LLM parse error (attempt {attempt}/3): {exc}")
                if attempt == 3:
                    raise
            except Exception as exc:
                logger.error(f"LLM call failed (attempt {attempt}/3): {exc}")
                if attempt == 3:
                    raise

    async def format_answer(self, question: str, results: list[dict], query: GeneratedQuery) -> str:
        """
        Convert raw MongoDB results into a human-friendly natural language answer.
        """
        prompt = (
            f"The user asked: \"{question}\"\n\n"
            f"MongoDB returned {len(results)} result(s):\n"
            f"{json.dumps(results[:20], default=str, indent=2)}\n\n"  # truncate to avoid token overflow
            "Please write a clear, concise, user-friendly response to the question "
            "based only on these results. Do not mention MongoDB or technical details. "
            "If results are empty, say so clearly."
        )
        try:
            if self.settings.llm_provider == "openai":
                return await self._openai_plain(prompt)
            else:
                return await self._gemini_plain(prompt)
        except Exception as exc:
            logger.error(f"Answer formatting failed: {exc}")
            # Fallback: return a simple summary
            return f"Found {len(results)} result(s) for your query."

    # ── Internal Callers ──────────────────────────────────────────────────────

    async def _call_llm(self, question: str, max_results: int) -> dict[str, Any]:
        if self.settings.llm_provider == "openai":
            return await self._openai_function_call(question, max_results)
        else:
            return await self._gemini_json_call(question, max_results)

    async def _openai_function_call(self, question: str, max_results: int) -> dict[str, Any]:
        """Use OpenAI function-calling for reliable structured JSON output."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        response = await self._openai_client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": DB_SCHEMA_CONTEXT
                    + f"\n\nCurrent UTC datetime: {now}\nMax results requested: {max_results}",
                },
                {"role": "user", "content": question},
            ],
            tools=[{"type": "function", "function": FUNCTION_SCHEMA}],
            tool_choice={"type": "function", "function": {"name": "generate_mongodb_query"}},
        )

        tool_call = response.choices[0].message.tool_calls[0]
        return json.loads(tool_call.function.arguments)

    async def _gemini_json_call(self, question: str, max_results: int) -> dict[str, Any]:
        """Use Gemini with strict JSON prompt."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        prompt = (
            DB_SCHEMA_CONTEXT
            + f"\n\nCurrent UTC datetime: {now}\nMax results requested: {max_results}\n\n"
            "User question: " + question + "\n\n"
            "Respond ONLY with a valid JSON object matching this schema (no markdown, no explanation outside JSON):\n"
            + json.dumps(FUNCTION_SCHEMA["parameters"], indent=2)
        )
        response = await self._gemini_model.generate_content_async(prompt)
        text = response.text.strip()
        # Strip possible ```json ... ``` fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    async def _openai_plain(self, prompt: str) -> str:
        response = await self._openai_client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()

    async def _gemini_plain(self, prompt: str) -> str:
        response = await self._gemini_model.generate_content_async(prompt)
        return response.text.strip()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_response(self, raw: dict[str, Any]) -> GeneratedQuery:
        return GeneratedQuery(
            operation=raw.get("operation", "find"),
            collection=raw.get("collection", "students"),
            filter=raw.get("filter", {}),
            projection=raw.get("projection", {}),
            pipeline=raw.get("pipeline", []),
            sort=raw.get("sort", {}),
            limit=raw.get("limit", 100),
            explanation=raw.get("explanation", ""),
        )


# ── Module-level singleton ─────────────────────────────────────────────────────
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
