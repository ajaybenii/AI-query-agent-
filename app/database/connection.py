"""
app/database/connection.py
───────────────────────────
Async MongoDB connection using Motor.
• Connection pooling (min 5, max 50)
• Automatic reconnect
• Index creation on startup
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client: AsyncIOMotorClient | None = None


async def connect_db() -> None:
    """Create Motor client and ensure indexes exist."""
    global _client
    settings = get_settings()

    logger.info(f"Connecting to MongoDB at {settings.mongodb_url} ...")
    _client = AsyncIOMotorClient(
        settings.mongodb_url,
        minPoolSize=5,
        maxPoolSize=50,
        serverSelectionTimeoutMS=5_000,
        connectTimeoutMS=10_000,
    )

    # Verify connection
    await _client.admin.command("ping")
    logger.info("MongoDB connected ✓")

    db = get_database()
    await _create_indexes(db)


async def disconnect_db() -> None:
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB disconnected")


def get_database() -> AsyncIOMotorDatabase:
    if _client is None:
        raise RuntimeError("MongoDB client not initialised. Call connect_db() first.")
    return _client[get_settings().mongodb_db_name]


async def _create_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all necessary indexes for performance."""
    logger.info("Creating MongoDB indexes ...")

    # students
    await db.students.create_index([("class", ASCENDING), ("section", ASCENDING)])
    await db.students.create_index([("roll_no", ASCENDING)], unique=True)

    # attendance
    await db.attendance.create_index([("student_id", ASCENDING), ("date", DESCENDING)])
    await db.attendance.create_index([("date", DESCENDING), ("status", ASCENDING)])
    await db.attendance.create_index([("class", ASCENDING), ("section", ASCENDING), ("date", DESCENDING)])

    # assignments
    await db.assignments.create_index([("due_date", ASCENDING)])
    await db.assignments.create_index([("class", ASCENDING), ("created_at", DESCENDING)])

    # submissions
    await db.submissions.create_index([("assignment_id", ASCENDING), ("student_id", ASCENDING)], unique=True)
    await db.submissions.create_index([("student_id", ASCENDING)])

    # exams
    await db.exams.create_index([("date", ASCENDING), ("class", ASCENDING)])

    # teachers
    await db.teachers.create_index([("email", ASCENDING)], unique=True)

    # classes
    await db.classes.create_index([("name", ASCENDING), ("section", ASCENDING)], unique=True)

    logger.info("Indexes created ✓")
