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
  main.py              # FastAPI app, lifespan (calls init_db + seeds admin), static mount
  config.py            # pydantic-settings from .env, lru_cached singleton
  database.py          # async engine, session factory, Base, get_db, init_db
  api/                 # REST routes: alerts, news, posts, dashboard, auth
  models/              # 7 SQLAlchemy models: NewsArticle, FacebookPost, DisasterAlert,
                       #   AuditLog, TaskLog, SystemSetting, User
  models/base.py       # ⚠️ just convenience re-exports. Real Base is in database.py.
  schemas/             # Pydantic request/response schemas
  services/            # alert_service, openai_service, ai_service, facebook_service,
                       #   phivolcs, news_api
  tasks/               # Celery app, beat schedule, scheduler tasks
  admin/               # Jinja2 templates and admin routes
```

## Key Database Behaviors

- **`get_db` auto-commits on success, auto-rollbacks on failure.** Do NOT call `db.commit()` inside route handlers that use `Depends(get_db)` — the dependency does it for you.
- **Celery tasks do NOT use `get_db`.** They use `async_session_factory()` directly and MUST call `await db.commit()` / `await db.rollback()` explicitly.
- **Startup calls `Base.metadata.create_all`.** Tables and native ENUM types are auto-created. Alembic is configured but not auto-run at startup.
- **Alembic uses SYNC URL** (`psycopg2` via `DATABASE_URL_SYNC`), while the app uses **ASYNC URL** (`asyncpg` via `DATABASE_URL`). Both are computed properties on `Settings`.
- **No Alembic migrations exist yet** (no `alembic/versions/` directory). Running `alembic revision --autogenerate` requires the DB to already exist with ENUM types created (e.g. by letting the app start once).
- **PostgreSQL native ENUM types** in models. Adding new enum values requires `ALTER TYPE ... ADD VALUE` in manual migrations — autogenerate cannot detect value additions.
- **Deduplication**: `filter_and_store_article` checks both `(title, source_url)` AND `content_hash` (SHA-256 of title + first 1000 chars of content). See `app/services/alert_service.py:21-35`.
- **UUID primary keys** on all tables via `sqlalchemy.dialects.postgresql.UUID`.

## Celery / Async Quirk

- Celery tasks are synchronous but the app uses `asyncpg`. Every task bridges this with `asyncio.run()` wrapping an inner async function.
- Beat schedule (in `celery_app.py`):
  - `poll_external_sources` — every `POLLING_INTERVAL_MINUTES` (default 60)
  - `process_pending_articles` — every 15 minutes (classify + summarize FILTERED articles with location_relevance_score ≥ 0.2, up to 10 at a time)
  - `publish_approved_posts` — every 30 minutes (publishes up to 5 APPROVED posts, retries up to 3 times before FAILED)
  - `retry_failed_posts` — every 10 minutes (retries FAILED posts with retry_count < 3)
- On-demand task: `process_article` — triggered by `POST /news/{id}/process`, processes a single article into a post
- Celery timezone is `Asia/Manila`, but code uses `datetime.utcnow()` for timestamps

## Data Flow (Article → Post → Publish)

1. **Poll**: PHIVOLCS (USGS earthquake API, mag ≥ 4.0), NewsAPI, 4 RSS feeds (PhilStar, Manila Bulletin, CNN PH, Inquirer) → filtered by `disaster_keywords_list`
2. **Store**: Deduplicated by title+URL and content hash → `news_articles` table (`FILTERED` status)
3. **Auto-process via beat** (every 15 min): AI classification → geographic relevance check (`ai_service.py` with Mountain Province priority list) → only articles with `location_relevance_score >= 0.2` proceed → OpenAI summarize → DALL-E 3 image → creates `facebook_posts` row (`PENDING_REVIEW`)
4. **Review**: Admin dashboard → approve/reject posts
5. **Publish**: `POST /posts/{id}/publish` or auto-publish via Celery beat → Meta Graph API → Facebook page

## Services (Singletons)

All service instances are module-level singletons:
- `openai_service` (`openai_service.py`) — GPT-4o-mini for summarize/caption, DALL-E 3 for images
- `ai_service` (`ai_service.py`) — gpt-4o-mini for disaster classification, geographic relevance assessment, location extraction. Has a hardcoded `GEOGRAPHIC_PRIORITY` list of Mountain Province municipalities and nearby areas.
- `facebook_service` (`facebook_service.py`) — Meta Graph API (photo post with caption; falls back to text-only)
- `phivolcs_service` (`phivolcs.py`) — USGS earthquake data (filters magnitude ≥ 4.0)
- `news_api_service` (`news_api.py`) — NewsAPI + 4 RSS feeds

## Env Vars

All required and optional env vars are documented in `.env.example`. Notable computed values:
- `DATABASE_URL` and `DATABASE_URL_SYNC` are **properties** on `Settings`, not raw env vars.
- `disaster_keywords_list` parses `DISASTER_KEYWORDS` (comma-separated) into a list.
- `OPENAI_ORG_ID` is referenced in `ai_service.py` (optional, not in `.env.example`).
- `IMAGE_MODEL` can be left empty to skip image generation.

## No Test/Lint/Typecheck Config

- No `pytest`, `mypy`, `ruff`, or `pre-commit` configuration exists in this repo.
- If you add any, document the commands here.