# SkillNexus — Developer Commands Reference

All commands assume you have `Docker Desktop` running and a terminal open.

---

## 🔴 Full Reset (Nuke Everything & Start Fresh)

Use this when you want a completely clean slate — wipes all DB data, volumes, containers.

```powershell
# 1. Go to backend folder
cd C:\Users\ajayg\Desktop\skillnexus\backend

# 2. Stop ALL containers and DELETE all volumes (postgres data, redis data)
docker compose down -v --remove-orphans

# 3. Start postgres, redis, and api fresh (in background)
docker compose up -d postgres redis api

# 4. Wait ~15 seconds for postgres to become healthy, then run migrations
docker exec skillnexus-api sh -c "python -m alembic upgrade head"

# 5. Start the frontend (in a separate terminal)
cd C:\Users\ajayg\Desktop\skillnexus\frontend\skill-nexus
npm run dev
```

---

## 🟡 Restart Backend Only (after Python code changes OR .env changes)

Use this after:
- Editing any `.py` file in `backend/app/`
- Changing **any value in `.env`** (API keys, secrets, config) — `.env` is loaded at container startup, so a restart picks up the new values automatically. No rebuild needed.

```powershell
cd C:\Users\ajayg\Desktop\skillnexus\backend
docker compose restart api
```

> **Tip:** Run `docker logs skillnexus-api --tail 20` after restart to verify there are no import errors.

---

## 🟢 Start Everything (normal daily startup)

Use this when containers exist but are stopped (e.g. after a PC reboot).

```powershell
# Backend
cd C:\Users\ajayg\Desktop\skillnexus\backend
docker compose up -d postgres redis api

# Frontend (separate terminal)
cd C:\Users\ajayg\Desktop\skillnexus\frontend\skill-nexus
npm run dev
```

---

## ⏹️ Stop Everything

```powershell
cd C:\Users\ajayg\Desktop\skillnexus\backend

# Stop containers but KEEP data (volumes preserved)
docker compose stop

# OR stop and remove containers (volumes still preserved)
docker compose down
```

---

## 🗄️ Migrations

> **Two very different operations — don't confuse them!**

### ① Create a new migration file (after changing models)
Run this **locally** on your machine (NOT inside Docker).
`uv` reads your local `.env` which connects to `localhost:5432`.

```powershell
cd C:\Users\ajayg\Desktop\skillnexus\backend
uv run alembic revision --autogenerate -m "describe_your_change"
```

This generates a new `.py` file in `alembic/versions/`. Commit it to git.

### ② Apply migrations to the DB

**Option A — locally** (if `uv` is installed on your machine):
```powershell
cd C:\Users\ajayg\Desktop\skillnexus\backend
uv run alembic upgrade head
```

**Option B — via Docker** (always works, `uv` not required):
```powershell
docker exec skillnexus-api sh -c "python -m alembic upgrade head"
```

### Check current migration version
```powershell
# Locally
uv run alembic current

# Via Docker
docker exec skillnexus-api sh -c "python -m alembic current"
```

### Rollback last migration
```powershell
# Locally
uv run alembic downgrade -1

# Via Docker
docker exec skillnexus-api sh -c "python -m alembic downgrade -1"
```


---

## 📋 Useful Docker Commands

### Check container status
```powershell
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### View live backend logs
```powershell
docker logs -f skillnexus-api
```

### View last N lines of backend logs
```powershell
docker logs skillnexus-api --tail 30
```

### View postgres logs
```powershell
docker logs -f skillnexus-postgres
```

### Open a shell inside the API container
```powershell
docker exec -it skillnexus-api sh
```

### Check if a Python import works inside the container
```powershell
docker exec skillnexus-api python -c "from app.services.progress_service import ProgressService; print('OK')"
```

---

## 🧪 Running Tests

```powershell
cd C:\Users\ajayg\Desktop\skillnexus\backend

# Run all tests
uv run pytest -v

# Run with coverage report
uv run pytest --cov=app --cov-report=html -v

# Run a specific test file
uv run pytest tests/test_progress.py -v
```

---

## 🌐 Service URLs

| Service    | URL                        |
|------------|----------------------------|
| Frontend   | http://localhost:5173       |
| Backend API | http://localhost:8000      |
| API Docs   | http://localhost:8000/docs  |
| pgAdmin    | http://localhost:5050       |
| PostgreSQL | localhost:5432              |
| Redis      | localhost:6379              |

> **pgAdmin** only starts with `docker compose --profile tools up -d pgadmin`

---

## ⚡ Quick Reference

| Goal | Command |
|------|---------  |
| Full reset + fresh start | `docker compose down -v --remove-orphans` → `up -d` → `migrate` |
| Restart backend after code change | `docker compose restart api` |
| Run migrations | `docker exec skillnexus-api sh -c "python -m alembic upgrade head"` |
| Start frontend dev server | `npm run dev` (in `frontend/skill-nexus/`) |
| View backend logs live | `docker logs -f skillnexus-api` |
| View last 30 log lines | `docker logs skillnexus-api --tail 30` |
| Stop everything | `docker compose stop` |
| Run tests | `uv run pytest -v` |
