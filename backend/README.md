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

### 2. Node Completion & Parent Auto-Complete

All assignments enforce **strict mode** — a quiz must be passed before any node can be marked as done.

| Rule | Detail |
|---|---|
| Enrollment | First root node (lowest `order_index`) automatically set to `in_progress` |
| Mark as Done | Requires `quiz_passed = true` (enforced server-side) |
| Parent auto-complete | If parent has **no resources** → auto-completes when all children are done |
| Parent with resources | Must pass its own quiz (NOT auto-completed) |
| XP award | +50 XP only when **all root nodes** are completed |

**Parent auto-complete logic** (backend, atomic within DB transaction):

```
Node marked done
  ↓
_auto_complete_parents() runs:
  For each ancestor:
    1. Does parent have resources? → YES → STOP (needs own quiz)
    2. Are ALL children done? → YES → auto-set parent to done
    3. Recurse upward to grandparent
```

The `ProgressService.update_node_progress` enforces these rules server-side — the frontend cannot bypass them.

---

### 3. Assignment & Enrollment

Admin assignment and self-enrollment follow the same pattern:

| Action | Creates Assignment | Initializes First Node | Strict Mode |
|---|---|---|---|
| Self-enroll | ✅ | ✅ (first root → `in_progress`) | `true` (default) |
| Admin assign | ✅ | ✅ (first root → `in_progress`) | `true` (default) |

**Un-assignment cleanup:**
When an admin removes an assignment, both the `UserRoadmapAssignment` AND all
`UserNodeProgress` records for that user+roadmap are deleted atomically.

---

### 4. Published Roadmap Restrictions

Once published via `POST /roadmaps/{id}/publish`, a roadmap becomes read-only:

| Operation | Allowed? |
|---|---|
| Edit title/description | ❌ 400 error |
| Add nodes | ❌ 400 error |
| Delete nodes | ❌ 400 error |
| Edit node content | ❌ 400 error |
| Update node positions | ✅ Allowed |
| Delete roadmap | ❌ 400 error |

Enforced in `roadmap_service.py` with an `is_published` check.

---

### 5. Gamification: Event-Based XP Ledger

```
point_transactions (append-only)
├── id
├── user_id
├── amount
├── event_type (node_complete | login | streak_bonus | quiz_pass | roadmap_complete)
├── description (e.g. "Completed roadmap: Learn Python")
├── reference_id (node UUID or roadmap UUID)
└── created_at

users
├── xp_balance (cached sum)
└── level (recalculated: xp_balance // 500 + 1)
```

| Event | XP | When |
|---|---|---|
| Daily login | +5 | On auth |
| Pass a quiz | +25 | Quiz score ≥ 2/3 |
| Complete roadmap | +50 | All root nodes done |
| 7-day streak | +100 bonus | Consecutive daily logins |

**Note:** XP is awarded once per roadmap completion. The description includes the roadmap title (e.g. `"Completed roadmap: Learn Python"`).

---

### 6. AI Prompt Strategy

**AI Tutor** — system prompt per node:
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

**AI Roadmap Generation** — `POST /roadmaps/generate`:
```
Prompt → LLM generates structured roadmap → saved to DB with all nodes
Uses same node structure as manual creation
```

---

### 7. Resume Analysis Pipeline

```
PDF Upload → Extract Text (pdfminer.six) → Sanitize PII → LLM Analysis → Save to DB
```

**PII Sanitization** (before sending to LLM):
- Phone numbers (international, US, Indian formats) → `[PHONE REMOVED]`
- Emails → `[EMAIL REMOVED]`
- Profile URLs (LinkedIn, GitHub, Twitter/X) → `[PROFILE URL REMOVED]`
- Addresses and ZIP/PIN codes → `[ADDRESS REMOVED]`

See `resume_service.py` → `_sanitize_resume_text()`.

---

### 8. Auth: Stateless Access + Stateful Refresh

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
docker exec skillnexus-api sh -c "python -m alembic upgrade head"
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

All endpoints are prefixed with `/api/v1`.

| Module | Key Endpoints |
|---|---|
| **Auth** | `POST /auth/register` · `/login` · `/refresh` · `/logout` |
| **Users** | `GET /users/me` · `PATCH /users/me` · `GET /users/leaderboard` · `GET /users/me/transactions` |
| **Roadmaps** | `GET /roadmaps` · `POST /roadmaps` · `GET /roadmaps/{id}` · `PATCH /roadmaps/{id}` |
| **Roadmaps** | `POST /roadmaps/{id}/publish` · `DELETE /roadmaps/{id}` · `POST /roadmaps/generate` |
| **Roadmaps** | `POST /roadmaps/{id}/nodes` · `PATCH /roadmaps/{id}/nodes/{nid}` · `DELETE /roadmaps/{id}/nodes/{nid}` |
| **Roadmaps** | `POST /roadmaps/request` (learner requests a roadmap) |
| **Progress** | `POST /progress/roadmaps/{id}/enroll` · `GET /progress/roadmaps/{id}` |
| **Progress** | `POST /progress/roadmaps/{id}/nodes/{nid}` · `GET /progress/roadmaps/{id}/nodes/{nid}` |
| **Chat** | `GET /chat/sessions/{nid}` · `GET /chat/sessions/{nid}/messages` · `POST /chat/sessions/{nid}/messages` |
| **Quiz** | `POST /chat/sessions/{nid}/quiz` · `POST /chat/sessions/{nid}/quiz/submit` |
| **Admin** | `POST /admin/assignments` · `GET /admin/assignments` · `PATCH /admin/assignments/{id}` · `DELETE /admin/assignments/{id}` |
| **Admin** | `GET /admin/analytics/dashboard` · `GET /admin/analytics/skill-gaps` · `GET /admin/analytics/users/{id}` |
| **Admin** | `GET /admin/roadmap-requests` · `PATCH /admin/roadmap-requests/{id}` |
| **Resume** | `POST /resume/upload` · `GET /resume/me` |

---

## 🏗️ Project Structure

```
backend/
├── app/
│   ├── api/deps.py              # JWT auth + role dependencies (CurrentUser, AdminUser, AdminOrManager)
│   ├── api/v1/routes/
│   │   ├── auth.py              # Registration, login, logout, refresh
│   │   ├── users.py             # Profile, leaderboard, transactions
│   │   ├── roadmaps.py          # CRUD, publish, generate, request
│   │   ├── progress.py          # Enrollment, node status, progress summary
│   │   ├── chat.py              # AI tutor, quiz generate/submit
│   │   ├── admin.py             # Assignments, analytics, roadmap requests
│   │   └── resume.py            # PDF upload + AI analysis
│   ├── core/
│   │   ├── config.py            # Settings from .env
│   │   ├── database.py          # Async SQLAlchemy engine + session
│   │   ├── security.py          # JWT encode/decode, password hashing
│   │   ├── redis.py             # Redis client
│   │   ├── llm.py               # LangChain LLM setup (Groq/Gemini)
│   │   └── exceptions.py        # Custom HTTP exceptions
│   ├── models/models.py         # SQLAlchemy ORM (User, Roadmap, RoadmapNode, etc.)
│   ├── schemas/                 # Pydantic v2 request/response schemas
│   │   ├── auth.py
│   │   ├── roadmap.py
│   │   ├── progress.py          # AssignmentCreateRequest (strict_mode=True default)
│   │   ├── chat.py
│   │   ├── analytics.py
│   │   └── base.py
│   ├── services/
│   │   ├── auth_service.py      # Login, register, token management
│   │   ├── roadmap_service.py   # CRUD + publish restrictions
│   │   ├── progress_service.py  # Node completion, parent auto-complete, XP, enrollment
│   │   ├── chat_service.py      # LLM chat + quiz generation/grading
│   │   ├── resume_service.py    # PDF extraction, PII sanitization, LLM analysis
│   │   └── ai_roadmap_generator.py  # AI roadmap creation from prompt
│   └── repositories/
│       ├── user_repository.py       # User CRUD, add_xp, leaderboard
│       ├── roadmap_repository.py    # Recursive CTE tree queries
│       └── progress_repository.py   # Assignment + node progress CRUD
├── alembic/versions/            # Migration files
├── tests/                       # Pytest suite
├── .env.example                 # Environment variable template
├── Dockerfile
└── docker-compose.yml
```

---

## 🔒 Security

- `GET /progress/roadmaps/{id}` returns **403** if user is not enrolled → frontend uses this as the authoritative enrollment check
- Users can only update progress on **assigned** roadmaps (403 otherwise)
- **All assignments enforce strict mode** — quiz pass required before marking Done
- Published roadmaps are **immutable** (400 on edit/add/delete attempts)
- Quiz correct answers stored **server-side only** (as hidden system chat messages)
- Resume text is **PII-sanitized** before LLM processing (phone, email, URLs, addresses removed)
- Passwords: bcrypt | Refresh tokens: SHA-256 hashed in DB
- `backend/.env` is in `.gitignore` — **never commit secrets**

---

## 🔑 Key Business Rules

| Rule | Implementation |
|---|---|
| All quizzes are mandatory | `strict_mode=True` default on all assignments |
| Parent auto-completes only if no resources | `_auto_complete_parents()` in `progress_service.py` |
| XP only on full roadmap completion | `_check_and_award_roadmap_xp()` checks all root nodes |
| Admin assignment = auto-enrollment | `create_assignment()` initializes first node |
| Admin un-assignment = full cleanup | `delete_assignment()` removes all progress records |
| Published = read-only | `roadmap_service.py` blocks edits when `is_published=True` |
| PII never reaches LLM | `_sanitize_resume_text()` strips PII before analysis |
