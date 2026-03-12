# 🤖 AI Query Agent — ERP Chatbot

A production-grade GenAI-powered query agent that converts **natural language questions into MongoDB queries**, executes them, and returns **human-friendly responses**.

---

## 📐 Architecture

```
User Question (NL)
      │
      ▼
┌─────────────────────┐
│   FastAPI REST API   │  ← POST /api/v1/query
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐       ┌──────────────────────┐
│    LLM Service       │──────▶│  OpenAI GPT-5.2      │
│  (Query Generator)   │      │  (Function Calling)  │
└────────┬────────────┘       └──────────────────────┘
         │  GeneratedQuery (structured JSON)
         ▼
┌─────────────────────┐
│   Query Executor     │  ← Security validation + sanitisation
│  (Safety Layer)      │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   MongoDB (Motor)    │  ← Async execution
│   erp_system DB      │
└────────┬────────────┘
         │  Raw results
         ▼
┌─────────────────────┐
│  Answer Formatter    │  ← LLM formats results → NL response
└────────┬────────────┘
         │
         ▼
    JSON Response
```

### Key Design Decisions
| Decision | Rationale |
|---|---|
| **OpenAI Function Calling** | Guarantees structured JSON output, no parsing guesswork |
| **Security whitelist** | Only allowed collections + pipeline stages can execute |
| **Date placeholder resolution** | LLM emits `$$TODAY_START$$` tokens; executor resolves them dynamically |
| **Motor (async)** | Non-blocking DB calls, scales with FastAPI's async model |
| **Pydantic v2 models** | Strict type validation on every request/response |
| **Loguru** | Structured JSON logs in production, coloured logs in dev |

---

## 🗃️ Database Schema

| Collection | Description |
|---|---|
| `students` | Student profiles (name, class, section, roll_no) |
| `teachers` | Teacher profiles (name, email, subjects) |
| `classes` | Class-section to teacher mappings |
| `attendance` | Daily attendance per student (present/absent/late) |
| `assignments` | Homework/project assignments with due dates |
| `submissions` | Student submissions linked to assignments |
| `exams` | Scheduled exams per class |

---

## 🚀 Local Setup

### Prerequisites
- Python 3.11+
- MongoDB 7.0 (local or Docker)
- OpenAI or Gemini API key

### Option A: Run with Docker (Recommended)

```bash
# 1. Clone the repo
git clone https://github.com/ajaybenii/AI-query-agent-.git
cd AI-query-agent-

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start all services
docker-compose up -d

# 4. Seed the database
docker exec erp_api python scripts/seed_data.py

# 5. Open API docs
open http://localhost:8000/docs
# Mongo Express UI at http://localhost:8081
```

### Option B: Run Locally

```bash
# 1. Install MongoDB (macOS)
brew tap mongodb/brew && brew install mongodb-community@7.0
brew services start mongodb-community@7.0

# 1. Install MongoDB (Ubuntu)
sudo apt install -y mongodb

# 2. Clone and setup Python environment
git clone https://github.com/your-username/ai-query-agent.git
cd ai-query-agent
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — add OPENAI_API_KEY or GEMINI_API_KEY

# 5. Seed the database
python scripts/seed_data.py

# 6. Create logs directory
mkdir -p logs

# 7. Start the API server
uvicorn app.main:app --reload --port 8000
```

### Verify Installation

```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status":"ok","mongodb":"connected","llm_provider":"openai"}
```

---

## 🚀 Deployment Guide (Render + Netlify)

This project is structured for easy deployment with the Backend on **Render** and the Frontend on **Netlify**.

### 1. Deploy Backend to Render
1. Push this repository to GitHub.
2. Go to [Render](https://render.com/), click **New +**, and select **Web Service**.
3. Connect your GitHub repository.
4. Render should automatically detect it's a Python app. Use these settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Click **Advanced** and add the following **Environment Variables**:
   - `MONGODB_URL`: Your MongoDB Atlas connection string (e.g., `mongodb+srv://...`)
   - `MONGODB_DB_NAME`: `erp_system`
   - `LLM_PROVIDER`: `openai`
   - `OPENAI_API_KEY`: Your OpenAI secret key
   - `OPENAI_MODEL`: `gpt-5.2`
   - `APP_ENV`: `production`
6. Deploy! Copy the Render URL once it's live (e.g., `https://ai-query-agent.onrender.com`).

### 2. Deploy Frontend to Netlify
1. Go to [Netlify](https://www.netlify.com/) and click **Add new site > Import an existing project**.
2. Connect your GitHub repository.
3. In the setup step, specify the **Base directory**:
   - **Base directory:** `frontend`
   - **Build command:** `npm run build`
   - **Publish directory:** `frontend/dist`
4. Click **Add environment variables** and add:
   - `VITE_API_URL`: The **Render URL** you copied in Step 1 (e.g., `https://ai-query-agent.onrender.com`).
5. Deploy the site! Netlify will build the React app and deploy it globally.

---

## 📡 API Reference

### `POST /api/v1/query`

Convert a natural language question into a MongoDB query and get an answer.

**Request:**
```json
{
  "question": "List all students in class 6",
  "max_results": 50
}
```

**Response:**
```json
{
  "question": "List all students in class 6",
  "answer": "There are 28 students in Class 6 across sections A, B, and C...",
  "query": {
    "operation": "find",
    "collection": "students",
    "filter": { "class": "6" },
    "projection": { "_id": 0, "name": 1, "class": 1, "section": 1, "roll_no": 1 },
    "pipeline": [],
    "sort": { "section": 1, "roll_no": 1 },
    "limit": 50,
    "explanation": "Find all students in class 6, sorted by section and roll number"
  },
  "results": [...],
  "total_results": 28,
  "execution_time_ms": 312.5
}
```

### `GET /api/v1/health`
Returns service health status.

### `GET /api/v1/examples`
Returns 15 sample questions grouped by complexity level.

---

## 💬 Example Queries & Outputs

### Level 1 – Basic

| Question | Sample Output |
|---|---|
| "List all students in class 6" | Returns 28 students with name, section, roll_no |
| "List all teachers in the system" | Returns 5 teachers with name, email, subjects |
| "Show all assignments created today" | Returns assignments with today's `created_at` |

### Level 2 – Filtering

```
Q: "Show students who were absent yesterday"
A: "12 students were absent yesterday: Aarav Sharma (6-A), Priya Verma (7-B)..."
```

```
Q: "Show students belonging to section A of class 6"
A: "There are 10 students in Class 6 Section A: Rohit Singh (Roll 1), ..."
```

### Level 3 – Aggregation

```
Q: "Count how many students were absent today"
A: "8 students were absent today."
```

```
Q: "Find the class with the highest number of absent students today"
A: "Class 8 has the highest absenteeism today with 4 absent students."
```

### Level 4 – Multi-Collection (Joins)

```
Q: "Show students who have not submitted any assignment"
A: "15 students have not submitted any assignments: Neha Patel (Class 7), ..."
```

```
Q: "Show attendance percentage of each student"
A: "Attendance percentages for all students:
    Aarav Sharma (Class 6-A): 92.3%
    Priya Verma (Class 6-A): 88.5%
    ..."
```

### Level 5 – Analytical

```
Q: "Show the top 5 students with the highest attendance percentage"
A: "The top 5 students by attendance:
    1. Kavya Singh (Class 9-B): 100%
    2. Manav Gupta (Class 10-A): 97.8%
    3. Shreya Patel (Class 8-C): 96.4%
    4. Arjun Kumar (Class 7-A): 95.2%
    5. Divya Sharma (Class 9-A): 94.1%"
```

---

## 🔒 Security Features

- **Collection whitelist** — Only 7 predefined collections are queryable
- **Pipeline stage whitelist** — Dangerous MongoDB stages are blocked
- **Operator blacklist** — `$where`, `$function`, `$accumulator` are rejected
- **Query depth limit** — Prevents infinite recursion in filter parsing
- **Result size cap** — Max 1000 results per query
- **Input validation** — All inputs validated via Pydantic before processing
- **Optional API key auth** — Set `API_SECRET_KEY` in `.env` to enable

---

## 🧪 Running Tests

```bash
pytest tests/ -v
# or with coverage
pytest tests/ -v --cov=app --cov-report=html
```

---

## 📁 Project Structure

```
ai-query-agent/
├── app/
│   ├── main.py              # FastAPI app factory + middleware
│   ├── config.py            # Pydantic settings from .env
│   ├── api/
│   │   └── routes/
│   │       └── query.py     # All API endpoints
│   ├── database/
│   │   └── connection.py    # Motor client + index creation
│   ├── models/
│   │   └── schemas.py       # Pydantic request/response/DB models
│   ├── services/
│   │   ├── llm_service.py   # OpenAI / Gemini abstraction
│   │   └── query_executor.py # Safe MongoDB query execution
│   └── utils/
│       └── logger.py        # Loguru configuration
├── scripts/
│   └── seed_data.py         # DB seeding with realistic data
├── tests/
│   └── test_query_executor.py
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 🔧 Configuration

| Variable | Default | Description |
|---|---|---|
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB_NAME` | `erp_system` | Database name |
| `LLM_PROVIDER` | `openai` | `openai` or `gemini` |
| `OPENAI_API_KEY` | — | OpenAI secret key |
| `OPENAI_MODEL` | `gpt-5.2` | OpenAI model to use |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `APP_ENV` | `development` | `development` or `production` |
| `API_SECRET_KEY` | _(empty)_ | Enable API key auth (optional) |

---

## 📈 Performance Notes

- Motor uses a connection pool (min 5, max 50 connections)
- All collections have compound indexes on common query patterns
- LLM calls are the primary latency (200–800ms typical)
- Results are capped at 1000 to prevent memory issues
