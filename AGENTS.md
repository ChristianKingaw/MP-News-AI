# AGENTS.md — Mountain Province Disaster Alert System

## Quickstart

```bash
cp .env.example .env   # fill in real keys
docker compose up -d   # api:8000, db:5432, redis:6379
```

## Stack & Entrypoints

- **Python 3.12**, FastAPI (async), SQLAlchemy 2.0 async (asyncpg), Celery, Redis, PostgreSQL 16
- App entrypoint: `app/main.py` → `uvicorn app.main:app`
- Celery worker: `celery -A app.tasks.celery_app worker --concurrency=2`
- Celery beat: `celery -A app.tasks.celery_app beat`
- Admin dashboard: `http://localhost:8000/admin` (Jinja2 server-rendered HTML, cookie-based JWT auth)

## Directory Map

```
app/
  main.py              # FastAPI app, lifespan (calls init_db + seeds admin), static mount
  config.py            # pydantic-settings from .env, lru_cached singleton
  database.py          # async engine, session factory, Base, get_db, init_db
  api/                 # REST routes: alerts, news, posts, dashboard, auth
  models/              # 7 SQLAlchemy models
  models/base.py       # ⚠️ convenience re-exports. Real Base is in database.py.
  schemas/             # Pydantic request/response schemas
  services/            # alert_service, openai_service, ai_service, facebook_service,
                       #   phivolcs, news_api, weather_service
  tasks/               # Celery app, beat schedule, scheduler tasks
  admin/               # Jinja2 templates and admin routes
```

## Key Database Behaviors

- **`get_db` auto-commits on success, auto-rollbacks on failure.** Do NOT call `db.commit()` inside route handlers using `Depends(get_db)` — the dependency does it for you.
- **Celery tasks do NOT use `get_db`.** They use `async_session_factory()` directly and MUST call `await db.commit()` / `await db.rollback()` explicitly. They also call `await engine.dispose()` at the start of every task before creating a session — this is required to avoid stale connection pool issues in long-running workers.
- **Startup calls `Base.metadata.create_all`.** Tables and native ENUM types are auto-created. Alembic is configured but not auto-run at startup.
- **Alembic uses SYNC URL** (`psycopg2` via `DATABASE_URL_SYNC`), while the app uses **ASYNC URL** (`asyncpg` via `DATABASE_URL`). Both are computed properties on `Settings`.
- **No Alembic migrations exist yet** (no `alembic/versions/` directory). `alembic revision --autogenerate` requires the DB to already exist with ENUM types created (e.g. let the app start once).
- **PostgreSQL native ENUM types** in models. Adding new enum values requires `ALTER TYPE ... ADD VALUE` in manual migrations — autogenerate cannot detect value additions.
- **Deduplication**: `filter_and_store_article` checks `(title, source_url)`, `content_hash` (SHA-256 of `title||first_1000_chars`), AND skips if the hash already exists in a SUMMARIZED/PUBLISHED article. See `app/services/alert_service.py:21-45`.
- **UUID primary keys** on all tables via `sqlalchemy.dialects.postgresql.UUID`.

## Celery / Async Quirk

- Celery tasks are synchronous but the app uses `asyncpg`. Every task bridges this with `asyncio.run()` wrapping an inner async function that calls `await engine.dispose()` first, then creates a session via `async_session_factory()`.
- Beat schedule (in `celery_app.py`):
  - `poll_external_sources` — every `POLLING_INTERVAL_MINUTES` (default 60)
  - `process_pending_articles` — every 15 min (classifies + summarizes FILTERED articles, creates APPROVED posts, **immediately attempts to publish each one**)
  - `publish_approved_posts` — every 30 min (publishes up to 5 APPROVED posts, retries ≤3 times before FAILED)
  - `retry_failed_posts` — every 10 min (retries FAILED posts with retry_count < 3)
- On-demand task: `process_article` — triggered by `POST /news/{id}/process`, processes a single article into a post
- Celery timezone is `Asia/Manila`; DB timestamps use `datetime.utcnow()` or `datetime.now(timezone.utc)` (both styles appear in the codebase).

## Data Flow (Article → Post → Publish)

1. **Poll**: PHIVOLCS (USGS earthquake API, mag ≥ 4.0), NewsAPI, NewsData.io, 3 RSS feeds (PhilStar, Inquirer, Rappler), OpenWeatherMap (current + 5-day forecast for Mountain Province) → filtered by `disaster_keywords_list`
2. **Store**: Deduplication → `news_articles` table with `FILTERED` status and `is_disaster_related=True` by default. Source image URLs extracted from RSS/NewsAPI articles are stored in `source_image_url`.
3. **Auto-process via beat** (every 15 min): AI classification (disasters + accidents + weather) → geographic relevance (Mountain Province municipalities ONLY, `location_relevance_score >= 0.4`) → OpenAI summarize → **source image capture** (preferred: download from article URL; fallback: DALL-E 3) → creates `facebook_posts` row with `APPROVED` status → **immediately attempts Facebook publish**
4. **Publish (catch-up)**: `publish_approved_posts` beat picks up any remaining APPROVED posts and publishes them
5. **Retry**: `retry_failed_posts` retries FAILED posts with retry_count < 3

⚠️ `process_article_workflow` creates posts with `APPROVED` status, not `PENDING_REVIEW`. The admin review step is manual — an admin can approve/reject posts via the dashboard before `publish_approved_posts` picks them up.

## Services (Singletons)

All service instances are module-level singletons:
- `openai_service` — GPT-4o-mini for summarize/caption, DALL-E 3 for images, source image download (uses separate `IMAGE_API_KEY`/`IMAGE_BASE_URL` if set)
- `ai_service` — GPT-4o-mini for disaster classification (now covers accidents, fires, and weather too), geographic relevance. Has a hardcoded `GEOGRAPHIC_PRIORITY` list (Mountain Province municipalities ONLY).
- `facebook_service` — Meta Graph API (photo post with caption; falls back to text-only)
- `phivolcs_service` — USGS earthquake data (filters magnitude ≥ 4.0)
- `news_api_service` — NewsAPI + 3 RSS feeds + NewsData.io. Extracts source image URLs from articles. Gracefully skips any source if no key is configured.
- `weather_service` — OpenWeatherMap (current + 5-day forecast for Mountain Province; produces weather alerts when hazardous conditions detected)

## Env Vars

- All required and optional env vars are documented in `.env.example`.
- `DATABASE_URL` and `DATABASE_URL_SYNC` are **properties** on `Settings`, not raw env vars.
- `disaster_keywords_list` parses `DISASTER_KEYWORDS` (comma-separated) into a list.
- `IMAGE_MODEL` can be left empty to skip image generation.
- `IMAGE_API_KEY` / `IMAGE_BASE_URL` allow a separate provider for image generation (defaults to main OpenAI client).
- `OPENWEATHERMAP_API_KEY` is optional; weather polling skips silently if not set.
- `NEWSDATA_API_KEY` is optional; NewsData.io polling skips silently if not set.
- `NEWSDATA_CATEGORIES` defaults to `crime,disaster,top,environment`.
- `WEATHER_LAT` / `WEATHER_LON` default to Mountain Province coordinates (17.09, 121.03).

## Admin Auth

- Admin dashboard at `/admin` uses **cookie-based JWT** (not bearer tokens). The `AdminAuthRequired` exception triggers a 303 redirect to `/admin/login`.
- API routes use `OAuth2PasswordBearer` (standard bearer token auth).
- Default admin credentials are seeded at startup from `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars.

## No Test/Lint/Typecheck Config

- No `pytest`, `mypy`, `ruff`, or `pre-commit` configuration exists in this repo.
- If you add any, document the commands here.