# AGENTS.md — Mountain Province Disaster Alert System

## Quickstart

```bash
cp .env.example .env   # fill in real keys
docker compose up -d   # api:8000, db:5432, redis:6379
```

## Stack & Entrypoints

- **Python 3.12**, FastAPI (async), SQLAlchemy 2.0 async (asyncpg), Celery, Redis, PostgreSQL 16
- App entrypoint: `app/main.py` → `uvicorn app.main:app`
- Celery worker: `celery -A app.tasks.celery_app worker`
- Celery beat: `celery -A app.tasks.celery_app beat`
- Admin dashboard: `http://localhost:8000/admin` (Jinja2 server-rendered HTML)

## Directory Map

```
app/
  main.py              # FastAPI app, lifespan (calls init_db), static mount
  config.py            # pydantic-settings from .env, lru_cached singleton
  database.py          # async engine, session factory, Base, get_db, init_db
  api/                 # REST routes: alerts, news, posts, dashboard
  models/              # SQLAlchemy models: NewsArticle, FacebookPost, DisasterAlert
  models/base.py       # ⚠️ NOT the SQLAlchemy Base — just convenience re-exports. Real Base is in database.py.
  schemas/             # Pydantic request/response schemas
  services/            # Business logic: alert_service, openai, facebook, phivolcs, news_api
  tasks/               # Celery app, beat schedule, poll/publish tasks
  admin/               # Jinja2 templates and admin routes
```

## Key Database Behaviors

- **`get_db` auto-commits on success, auto-rollbacks on failure.** Do NOT call `db.commit()` inside route handlers that use `Depends(get_db)` — the dependency does it for you.
- **Celery tasks do NOT use `get_db`.** They use `async_session_factory()` directly and MUST call `await db.commit()` / `await db.rollback()` explicitly. See `app/tasks/scheduler.py` for the pattern.
- **Startup calls `Base.metadata.create_all`.** Tables and native ENUM types are auto-created. Alembic is configured but not auto-run at startup.
- **Alembic uses SYNC URL** (`psycopg2` via `DATABASE_URL_SYNC`), while the app uses **ASYNC URL** (`asyncpg` via `DATABASE_URL`). Both are computed properties on `Settings` (`app/config.py:39-51`).
- **No Alembic migrations exist yet** (empty `alembic/versions/`). Running `alembic revision --autogenerate -m "init"` requires the DB to already exist with ENUM types created (e.g. by letting the app start once).
- **PostgreSQL native ENUM types** in models (e.g. `Enum(SourceType, name="source_type_enum")`). Adding new enum values requires `ALTER TYPE ... ADD VALUE` in manual migrations — autogenerate cannot detect value additions.
- **Deduplication**: `filter_and_store_article` checks for existing `(title, source_url)` pairs before inserting.
- **UUID primary keys** on all tables via `sqlalchemy.dialects.postgresql.UUID`.

## Celery / Async Quirk

- Celery tasks are synchronous but the app uses `asyncpg`. Every task bridges this with `asyncio.run()` wrapping an inner async function. See `app/tasks/scheduler.py:43-44`.
- Beat schedule (in `celery_app.py`):
  - `poll_external_sources` — runs every `POLLING_INTERVAL_MINUTES` (default 60)
  - `publish_approved_posts` — runs every 30 minutes, publishes up to 5 approved posts

## Data Flow (Article → Post → Publish)

1. **Poll**: PHIVOLCS API, NewsAPI, RSS feeds → filtered by `disaster_keywords_list`
2. **Store**: Deduplicated → `news_articles` table (`FILTERED` status)
3. **Process**: `POST /news/{id}/process` or `process_article` Celery task → OpenAI summarize → generate caption → DALL-E 3 image → creates `facebook_posts` row (`PENDING_REVIEW`)
4. **Review**: Admin dashboard → approve/reject posts
5. **Publish**: `POST /posts/{id}/publish` or auto-publish via Celery beat → Meta Graph API → Facebook page

## Services (Singletons)

All service instances are module-level singletons, not DI:
- `openai_service` (`openai_service.py`) — GPT-4o-mini for text, DALL-E 3 for images
- `facebook_service` (`facebook_service.py`) — Meta Graph API (photo post with caption; falls back to text-only)
- `phivolcs_service` (`phivolcs.py`) — earthquake data (filters magnitude ≥ 4.0)
- `news_api_service` (`news_api.py`) — NewsAPI + 4 RSS feeds (PhilStar, Manila Bulletin, CNN PH, Inquirer)

## Static Files & Images

- DALL-E 3 images saved to `static/images/`, served at `/static` via FastAPI `StaticFiles` mount.
- Docker volume `generated_images` maps to `/app/static/images` for persistence across container restarts.
- `static/images/*.png` and `*.jpg` are gitignored.

## No Test/Lint/Typecheck Config

- No `pytest`, `mypy`, `ruff`, or `pre-commit` configuration exists in this repo.
- If you add any, document the commands here.

## Env Vars

All required and optional env vars are documented in `.env.example`. Notable computed values:
- `DATABASE_URL` and `DATABASE_URL_SYNC` are **properties** on `Settings` (`app/config.py:39-51`), not raw env vars.
- `disaster_keywords_list` parses `DISASTER_KEYWORDS` (comma-separated) into a list (`app/config.py:54-55`).