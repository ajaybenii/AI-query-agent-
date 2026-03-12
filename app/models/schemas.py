"""
app/models/schemas.py
──────────────────────
Pydantic v2 models (request / response / DB documents).
All ObjectIds are serialised as strings for API consumers.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Helpers ─────────────────────────────────────────────────────────────────

class PyObjectId(str):
    """Coerce ObjectId to/from str for Pydantic."""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        if isinstance(v, str) and ObjectId.is_valid(v):
            return v
        raise ValueError(f"Invalid ObjectId: {v}")


# ── Enums ────────────────────────────────────────────────────────────────────

class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"


class SubmissionStatus(str, Enum):
    SUBMITTED = "submitted"
    LATE = "late"
    PENDING = "pending"


# ── Student ───────────────────────────────────────────────────────────────────

class StudentCreate(BaseModel):
    name: str
    class_name: str = Field(..., alias="class")
    section: str
    roll_no: int
    email: str
    phone: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class Student(StudentCreate):
    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


# ── Teacher ───────────────────────────────────────────────────────────────────

class TeacherCreate(BaseModel):
    name: str
    email: str
    subjects: list[str]
    phone: str | None = None


class Teacher(TeacherCreate):
    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


# ── Class ─────────────────────────────────────────────────────────────────────

class ClassCreate(BaseModel):
    name: str            # e.g. "6", "7", "10"
    section: str         # e.g. "A", "B"
    subject: str
    teacher_id: str


class Class(ClassCreate):
    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


# ── Attendance ────────────────────────────────────────────────────────────────

class AttendanceCreate(BaseModel):
    student_id: str
    student_name: str
    class_name: str = Field(..., alias="class")
    section: str
    date: datetime
    status: AttendanceStatus

    model_config = ConfigDict(populate_by_name=True)


class Attendance(AttendanceCreate):
    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


# ── Assignment ────────────────────────────────────────────────────────────────

class AssignmentCreate(BaseModel):
    title: str
    description: str
    class_name: str = Field(..., alias="class")
    section: str | None = None   # None means all sections
    subject: str
    teacher_id: str
    due_date: datetime

    model_config = ConfigDict(populate_by_name=True)


class Assignment(AssignmentCreate):
    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


# ── Submission ────────────────────────────────────────────────────────────────

class SubmissionCreate(BaseModel):
    assignment_id: str
    student_id: str
    student_name: str
    class_name: str = Field(..., alias="class")
    status: SubmissionStatus = SubmissionStatus.SUBMITTED
    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


class Submission(SubmissionCreate):
    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


# ── Exam ──────────────────────────────────────────────────────────────────────

class ExamCreate(BaseModel):
    title: str
    subject: str
    class_name: str = Field(..., alias="class")
    section: str | None = None
    date: datetime
    duration_minutes: int = 120

    model_config = ConfigDict(populate_by_name=True)


class Exam(ExamCreate):
    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(populate_by_name=True)


# ── API Request / Response ────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000, description="Natural language question")
    max_results: int = Field(default=100, ge=1, le=1000, description="Max rows to return")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"question": "List all students in class 6", "max_results": 50}
        }
    )


class GeneratedQuery(BaseModel):
    """The structured MongoDB query produced by the LLM."""
    operation: str          # find | aggregate | count
    collection: str
    filter: dict[str, Any] = Field(default_factory=dict)
    projection: dict[str, Any] = Field(default_factory=dict)
    pipeline: list[dict[str, Any]] = Field(default_factory=list)
    sort: dict[str, Any] = Field(default_factory=dict)
    limit: int = 100
    explanation: str = ""


class QueryResponse(BaseModel):
    question: str
    answer: str
    query: GeneratedQuery
    results: list[dict[str, Any]]
    total_results: int
    execution_time_ms: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "List all students in class 6",
                "answer": "There are 3 students in class 6: Alice, Bob, and Charlie.",
                "total_results": 3,
                "execution_time_ms": 120.5,
            }
        }
    )


class HealthResponse(BaseModel):
    status: str
    mongodb: str
    llm_provider: str
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str | None = None
