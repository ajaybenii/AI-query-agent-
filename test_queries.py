import asyncio
import json
import httpx

API_URL = "http://localhost:8000/api/v1/query"

QUERIES = [
    "List all students in class 6",
    "Show the attendance of Aarav Sharma for yesterday",
    "List all teachers in the system",
    "Show all assignments created today",
    "Show students who were absent yesterday",
    "List assignments due this month",
    "Show students belonging to section A of class 6",
    "Show all exams scheduled this month",
    "Count how many students were absent yesterday",
    "Show the number of assignments submitted per class",
    "Find the class with the highest number of absent students yesterday",
    "Show students who have not submitted an assignment",
    "List teachers and the classes they teach",
    "Show attendance percentage of each student",
    "Show the top 5 students with the highest attendance percentage"
]

async def run_queries():
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, query in enumerate(QUERIES, 1):
            print(f"\n--- [Level {i}] {query} ---")
            try:
                resp = await client.post(API_URL, json={"question": query})
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"✅ Answer: {data['answer']}")
                    print(f"📊 Results count: {data['total_results']}")
                else:
                    print(f"❌ Error: {resp.status_code} - {resp.text}")
            except Exception as e:
                print(f"⚠️ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(run_queries())
