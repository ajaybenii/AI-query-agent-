"""
scripts/seed_data.py
─────────────────────
Seeds MongoDB with realistic ERP data for testing all 15 query levels.

Run: python scripts/seed_data.py
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

# ── Config ────────────────────────────────────────────────────────────────────
MONGODB_URL = "mongodb://localhost:27017"
DB_NAME = "erp_system"

# ── Sample Data ────────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Aarav", "Aditya", "Arjun", "Bhavya", "Chirag", "Deepika", "Divya",
    "Gaurav", "Harsh", "Ishaan", "Kavya", "Kiran", "Manav", "Neha",
    "Nikhil", "Pooja", "Priya", "Rahul", "Raj", "Riya", "Rohit", "Sakshi",
    "Sanjay", "Shreya", "Siddharth", "Sneha", "Tanvi", "Varun", "Vikram", "Yash",
]

LAST_NAMES = [
    "Sharma", "Verma", "Singh", "Gupta", "Patel", "Kumar", "Joshi",
    "Mehta", "Shah", "Yadav", "Nair", "Pillai", "Reddy", "Iyer", "Kapoor",
]

SUBJECTS = ["Mathematics", "Science", "English", "Hindi", "Social Studies", "Computer Science"]

CLASSES = ["6", "7", "8", "9", "10"]
SECTIONS = ["A", "B", "C"]

now = datetime.now(timezone.utc)


def random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


async def seed():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]

    print("🗑️  Dropping existing collections ...")
    for col in ["students", "teachers", "classes", "attendance", "assignments", "submissions", "exams"]:
        await db[col].drop()

    # ── Teachers ─────────────────────────────────────────────────────────────
    print("👩‍🏫 Seeding teachers ...")
    teachers = []
    teacher_names = [
        ("Mrs. Sunita Sharma", "sunita@school.edu", ["Mathematics", "Science"]),
        ("Mr. Rajesh Verma", "rajesh@school.edu", ["English", "Hindi"]),
        ("Mrs. Anita Patel", "anita@school.edu", ["Social Studies", "Computer Science"]),
        ("Mr. Vijay Kumar", "vijay@school.edu", ["Mathematics", "Computer Science"]),
        ("Mrs. Priya Mehta", "priya@school.edu", ["Science", "English"]),
    ]
    for name, email, subjects in teacher_names:
        result = await db.teachers.insert_one({
            "name": name,
            "email": email,
            "subjects": subjects,
            "phone": f"98{random.randint(10000000, 99999999)}",
            "created_at": now,
        })
        teachers.append({"_id": result.inserted_id, "name": name, "subjects": subjects})

    # ── Classes ───────────────────────────────────────────────────────────────
    print("🏫 Seeding classes ...")
    classes_data = []
    teacher_idx = 0
    for cls in CLASSES:
        for section in SECTIONS:
            subject = SUBJECTS[teacher_idx % len(SUBJECTS)]
            teacher = teachers[teacher_idx % len(teachers)]
            result = await db.classes.insert_one({
                "name": cls,
                "section": section,
                "subject": subject,
                "teacher_id": teacher["_id"],
                "created_at": now,
            })
            classes_data.append({"_id": result.inserted_id, "name": cls, "section": section, "teacher": teacher})
            teacher_idx += 1

    # ── Students ──────────────────────────────────────────────────────────────
    print("👨‍🎓 Seeding students ...")
    students = []
    roll_counter = 1

    for cls in CLASSES:
        for section in SECTIONS:
            # 8-12 students per class-section
            num_students = random.randint(8, 12)
            for _ in range(num_students):
                name = random_name()
                result = await db.students.insert_one({
                    "name": name,
                    "class": cls,
                    "section": section,
                    "roll_no": roll_counter,
                    "email": f"student{roll_counter}@school.edu",
                    "phone": f"99{random.randint(10000000, 99999999)}",
                    "created_at": now,
                })
                students.append({
                    "_id": result.inserted_id,
                    "name": name,
                    "class": cls,
                    "section": section,
                    "roll_no": roll_counter,
                })
                roll_counter += 1

    print(f"   → {len(students)} students created")

    # ── Attendance (last 30 days) ─────────────────────────────────────────────
    print("📋 Seeding attendance records (30 days) ...")
    attendance_docs = []
    for day_offset in range(30):
        date = day_start(now - timedelta(days=day_offset))
        # Skip weekends
        if date.weekday() >= 5:
            continue
        for student in students:
            # ~85% attendance rate
            status = "present" if random.random() < 0.85 else "absent"
            attendance_docs.append({
                "student_id": student["_id"],
                "student_name": student["name"],
                "class": student["class"],
                "section": student["section"],
                "date": date,
                "status": status,
                "created_at": date,
            })

    if attendance_docs:
        await db.attendance.insert_many(attendance_docs)
    print(f"   → {len(attendance_docs)} attendance records created")

    # ── Assignments ───────────────────────────────────────────────────────────
    print("📝 Seeding assignments ...")
    assignment_docs = []
    assignment_ids = []

    assignment_titles = [
        "Chapter 1 Problems", "Essay Writing", "Lab Report", "Practice Questions",
        "Holiday Homework", "Project Work", "Worksheet A", "Revision Notes",
    ]

    for cls in CLASSES:
        for i, title in enumerate(assignment_titles[:4]):
            # Mix of past, today, and future assignments
            offset = random.choice([-7, -3, -1, 0, 2, 5, 7, 10])
            created_at = day_start(now + timedelta(days=offset - 5))
            due = day_start(now + timedelta(days=offset))
            subject = SUBJECTS[i % len(SUBJECTS)]
            teacher = teachers[i % len(teachers)]

            result = await db.assignments.insert_one({
                "title": f"{title} - {subject}",
                "description": f"Complete {title.lower()} for {subject} class {cls}",
                "class": cls,
                "section": None,  # all sections
                "subject": subject,
                "teacher_id": teacher["_id"],
                "due_date": due,
                "created_at": created_at,
            })
            assignment_ids.append({
                "_id": result.inserted_id,
                "class": cls,
                "title": f"{title} - {subject}",
            })

    print(f"   → {len(assignment_ids)} assignments created")

    # ── Submissions ───────────────────────────────────────────────────────────
    print("✅ Seeding submissions ...")
    submission_docs = []
    seen = set()  # avoid duplicate (assignment_id, student_id)

    for assignment in assignment_ids:
        class_students = [s for s in students if s["class"] == assignment["class"]]
        # ~70% of students submit each assignment
        submitters = random.sample(class_students, int(len(class_students) * 0.7))
        for student in submitters:
            key = (str(assignment["_id"]), str(student["_id"]))
            if key in seen:
                continue
            seen.add(key)
            submission_docs.append({
                "assignment_id": assignment["_id"],
                "student_id": student["_id"],
                "student_name": student["name"],
                "class": student["class"],
                "status": "submitted",
                "submitted_at": now - timedelta(hours=random.randint(1, 72)),
                "created_at": now,
            })

    if submission_docs:
        await db.submissions.insert_many(submission_docs)
    print(f"   → {len(submission_docs)} submissions created")

    # ── Exams ─────────────────────────────────────────────────────────────────
    print("📅 Seeding exams ...")
    exam_docs = []
    exam_names = ["Mid-Term", "Unit Test", "Final Exam", "Quarterly"]

    for cls in CLASSES:
        for i, exam_name in enumerate(exam_names):
            offset = random.choice([-10, -5, 5, 10, 15, 20, 25])
            exam_docs.append({
                "title": f"{exam_name} - {SUBJECTS[i % len(SUBJECTS)]}",
                "subject": SUBJECTS[i % len(SUBJECTS)],
                "class": cls,
                "section": None,
                "date": day_start(now + timedelta(days=offset)),
                "duration_minutes": 120,
                "created_at": now,
            })

    await db.exams.insert_many(exam_docs)
    print(f"   → {len(exam_docs)} exams created")

    client.close()
    print("\n✅ Seeding complete!")
    print(f"   Students: {len(students)}")
    print(f"   Teachers: {len(teachers)}")
    print(f"   Attendance records: {len(attendance_docs)}")
    print(f"   Assignments: {len(assignment_ids)}")
    print(f"   Submissions: {len(submission_docs)}")
    print(f"   Exams: {len(exam_docs)}")


if __name__ == "__main__":
    asyncio.run(seed())
