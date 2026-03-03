# SkillNexus Backend API

AI-Powered Enterprise Learning & Development Platform — FastAPI Backend

---

## 🗂️ Architecture Decisions

### 1. Tree/Graph Strategy: Adjacency List + Recursive CTE

The roadmap node hierarchy is stored as an **Adjacency List**:

```
roadmap_nodes
├── id (UUID PK)
├── roadmap_id (FK → roadmaps)
├── parent_id (FK → roadmap_nodes, nullable = root node)  ← Self-referential
├── title
├── order_index     ← used for linear progression ordering
├── ...
```

**Why Adjacency List?**
- Simple to understand and maintain
- Fast inserts (just set `parent_id`, no path or closure table updates)
- PostgreSQL's `WITH RECURSIVE` handles unlimited depth efficiently

**The Recursive CTE query** (in `roadmap_repository.py`):
```sql
WITH RECURSIVE node_tree AS (
    -- Anchor: root nodes
    SELECT id, parent_id, title, ..., 0 AS depth
    FROM roadmap_nodes WHERE roadmap_id = $1 AND parent_id IS NULL

    UNION ALL

    -- Recursive: children
    SELECT n.id, n.parent_id, n.title, ..., nt.depth + 1
    FROM roadmap_nodes n
    INNER JOIN node_tree nt ON n.parent_id = nt.id
)
SELECT * FROM node_tree ORDER BY path, order_index
```

The flat result is assembled into a nested tree in Python in O(n) using a hash map (see `roadmap_service.py` → `_build_tree()`).

**Performance**: Fetching a 50+ node roadmap = 1 DB round-trip, typically < 50ms.

---

### 2. Progressive Node Unlocking

Nodes unlock **sequentially by `order_index`**:

| Rule | Detail |
|---|---|
| Enrollment | First root node (lowest `order_index`) is automatically set to `in_progress` |
| Unlock next | Previous node must be `done` **and** `quiz_passed = true` |
| Root nodes | Always unlockable for enrolled users without parent checks |
| Strict mode | `done` status requires `quiz_passed = true` (admin-controlled per assignment) |

The `ProgressService.update_node_progress` enforces these rules server-side — the frontend cannot bypass them.

---

### 3. Gamification: Event-Based XP Ledger

```
point_transactions (append-only)
├── id
├── user_id
├── amount
├── event_type (node_complete | login | streak_bonus | quiz_pass | ...)
├── reference_id (node UUID or roadmap UUID)
└── created_at

users
├── xp_balance (cached sum)
└── level (recalculated: xp_balance // 500 + 1)
```

| Event | XP |
|---|---|
| Daily login | +5 |
| Complete a node | +50 |
| 7-day streak | +100 bonus |
| Pass a quiz | +25 |

---

### 4. AI Prompt Strategy

System prompt per node:
```
You are an expert corporate trainer. The user is currently studying '{node_title}'
in the '{roadmap_title}' learning roadmap. Keep answers concise and practical.
```

Chat history stored per-node in DB. Last 20 messages loaded as LangChain message objects per call.

**Quiz security**: Correct answers are stored as a `system` role message (`__QUIZ_ANSWERS__:{json}`) in the chat session — never included in responses sent to the client. Grading is done entirely server-side in `ChatService.submit_quiz`.

**Quiz answer format** (`QuizAnswerSubmission`):
```json
{ "answers": { "1": "A", "2": "C", "3": "B" } }
```
Keys are `question_number` (string), values are option keys (`"A"` / `"B"` / `"C"` / `"D"`).

---

### 5. Auth: Stateless Access + Stateful Refresh

| Token | Storage | Lifetime | Revocable |
|---|---|---|---|
| Access JWT | Client only | 30 min | No |
| Refresh JWT | SHA-256 hash in DB | 30 days | Yes |

---

## 🚀 Quick Start

```bash
cp .env.example .env
# Fill in GROQ_API_KEY, DATABASE_URL, SECRET_KEY, etc.

docker compose up -d
docker compose run --rm migrate
```

API: http://localhost:8000 | Docs: http://localhost:8000/docs

### Local Dev

```bash
uv sync --all-extras
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

### Tests

```bash
uv run pytest -v
uv run pytest --cov=app --cov-report=html -v
```

---

## 📡 API Reference

| Module | Key Endpoints |
|---|---|
| **Auth** | POST /auth/register, /auth/login, /auth/refresh, /auth/logout |
| **Users** | GET /users/me, GET /users/leaderboard |
| **Roadmaps** | GET /roadmaps, POST /roadmaps, GET /roadmaps/{id}, POST /roadmaps/generate (AI) |
| **Progress** | POST /progress/roadmaps/{id}/enroll |
| **Progress** | GET /progress/roadmaps/{id}, POST /progress/roadmaps/{id}/nodes/{nid} |
| **Chat** | POST /chat/sessions/{node_id}/messages |
| **Quiz** | POST /chat/sessions/{node_id}/quiz, POST /chat/sessions/{node_id}/quiz/submit |
| **Admin** | POST /admin/assignments, GET /admin/analytics/dashboard |
| **Resume** | POST /resume/upload |

---

## 🏗️ Project Structure

```
backend/
├── app/
│   ├── api/deps.py              # JWT auth + role dependencies
│   ├── api/v1/routes/           # Route modules
│   ├── core/                    # Config, DB, security, Redis, exceptions
│   ├── models/models.py         # SQLAlchemy ORM models (10 tables)
│   ├── schemas/                 # Pydantic v2 schemas
│   ├── services/                # Business logic
│   └── repositories/            # DB query layer
├── alembic/versions/            # Migrations
├── tests/                       # Pytest suite
├── .env.example                 # Environment variable template
├── Dockerfile
└── docker-compose.yml
```

---

## 🔒 Security

- `GET /progress/roadmaps/{id}` returns **403** if user is not enrolled → frontend uses this as the authoritative enrollment check
- Users can only update progress on **assigned** roadmaps (403 otherwise)
- **Strict Mode**: requires quiz pass before marking Done
- Quiz correct answers stored **server-side only** (as hidden system chat messages)
- Passwords: bcrypt | Refresh tokens: SHA-256 hashed in DB
- `backend/.env` is in `.gitignore` — **never commit secrets**

## 🌟 Bonus Features

1. **AI Roadmap Generator** — `POST /api/v1/roadmaps/generate`
2. **Strict Mode** — toggle on assignments via `PATCH /api/v1/admin/assignments/{id}`
3. **Resume Skill Extraction** — `POST /api/v1/resume/upload`
