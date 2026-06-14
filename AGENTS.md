# AGENTS.md — Mountain Province Disaster Alert System

## Quickstart

```bash
cp .env.example .env   # fill in real keys
docker compose up -d   # api:8000, db:5432, redis:6379
```

## Stack & Entrypoints

- **Python 3.12**, FastAPI (async), SQLAlchemy 2.0 async (asyncpg), Celery, Redis, PostgreSQL 16
- App entrypoint: `app/main.py` → `uvicorn app.main:app` (Dockerfile includes `--reload`)
- Celery worker: `celery -A app.tasks.celery_app worker --concurrency=2`
- Celery beat: `celery -A app.tasks.celery_app beat`
- Admin dashboard: `http://localhost:8000/admin` (Jinja2 server-rendered HTML, cookie-based JWT auth)

## Directory Map

```
app/
  main.py              # FastAPI app, lifespan (calls init_db + seeds admin), static mount
  config.py            # pydantic-settings from .env, @lru_cache singleton
  database.py          # async engine, session factory, Base, get_db, init_db
  api/                 # REST routes: alerts, news, posts, dashboard, auth
  models/              # 7 SQLAlchemy models
  models/base.py       # Convenience re-exports. Real Base is in database.py.
  schemas/             # Pydantic request/response schemas
  services/            # alert_service, openai_service, ai_service, facebook_service,
                       #   phivolcs, news_api, weather_service
  tasks/               # Celery app, beat schedule, scheduler tasks
  admin/               # Jinja2 templates and admin routes
```

## Key Database Behaviors

- **`get_db` auto-commits on success, auto-rollbacks on failure.** Do NOT call `db.commit()` inside route handlers using `Depends(get_db)` — the dependency does it for you.
- **Celery tasks do NOT use `get_db`.** They use `async_session_factory()` directly and MUST call `await db.commit()` / `await db.rollback()` explicitly.
- **Startup calls `Base.metadata.create_all` via `init_db()`.** Tables and native ENUM types are auto-created. Models must be imported before `create_all` runs (done in `init_db()`).
- **Alembic uses SYNC URL** (`psycopg2` via `DATABASE_URL_SYNC`), while the app uses **ASYNC URL** (`asyncpg` via `DATABASE_URL`). Both are computed properties on `Settings`.
- **No Alembic migrations exist yet** (no `alembic/versions/` directory). `alembic revision --autogenerate` requires the DB to already exist with ENUM types created (e.g. let the app start once).
- **PostgreSQL native ENUM types** in models. Adding new enum values requires `ALTER TYPE ... ADD VALUE` in manual migrations — autogenerate cannot detect value additions.
- **Deduplication** in `filter_and_store_article` (`app/services/alert_service.py:67-113`): checks `(title, source_url)` uniqueness first, then `content_hash` (SHA-256 of `title||first_1000_chars`), then skips if hash already exists in a SUMMARIZED/PUBLISHED article.
- **UUID primary keys** on all tables via `sqlalchemy.dialects.postgresql.UUID`.

## Celery / Async Quirk

- Celery tasks are synchronous but the app uses `asyncpg`. Scheduler tasks bridge this with a **module-level event loop** (`_LOOP = asyncio.new_event_loop()` at top of `app/tasks/scheduler.py`) and a `_run_async(coro)` helper. The same loop is reused across all beat-invoked tasks.
- The on-demand `process_article_task` creates its own async wrapper inline (no event loop at module scope).
- Beat schedule (in `celery_app.py`):
  - `poll_external_sources` — every `POLLING_INTERVAL_MINUTES` (default 60)
  - `process_pending_articles` — every 15 min (classifies + summarizes FILTERED articles, creates APPROVED posts, **immediately attempts to publish each one**)
  - `publish_approved_posts` — every 30 min (publishes ALL APPROVED posts, retries ≤3 times before FAILED; no count limit in code despite config having `MAX_POSTS_PER_HOUR`)
  - `retry_failed_posts` — every 10 min (retries FAILED posts with retry_count < 3)
- On-demand task: `process_article_task` — triggered by `POST /news/{id}/process` (supports both sync and async modes via `?async_mode=` query param)
- Celery timezone is `Asia/Manila`; DB timestamps use both `datetime.utcnow()` and `datetime.now(timezone.utc)` (both styles appear in codebase).
- **Beat schedule persistence**: `celerybeat-schedule` file in repo root (gitignored) persists the Celery beat schedule across restarts.

## Data Flow (Article → Post → Publish)

1. **Poll**: PHIVOLCS (USGS earthquake API, mag ≥ 4.0, within 300km of MP), NewsAPI, NewsData.io, 3 RSS feeds (PhilStar, Inquirer, Rappler), OpenWeatherMap (current + 5-day forecast for Mountain Province) → keyword-filtered by `disaster_keywords_list`
2. **Store**: Deduplication → `news_articles` table with `FILTERED` status and `is_disaster_related=True` by default. Source image URLs extracted from RSS/NewsAPI articles are stored in `source_image_url`.
3. **Auto-process via beat** (every 15 min): AI classification (disasters + accidents + weather) → geographic relevance check → OpenAI summarize → **source image capture** (priority: download from article URL → DALL-E 3 → HuggingFace FLUX.1-schnell) → creates `facebook_posts` row with `APPROVED` status → **immediately attempts Facebook publish**
4. **Publish (catch-up)**: `publish_approved_posts` beat picks up any remaining APPROVED posts and publishes them (text-only fallback if image missing/fails)
5. **Retry**: `retry_failed_posts` retries FAILED posts with retry_count < 3

**Geographic relevance thresholds** (actual code behavior):
- **PHIVOLCS articles**: `location_relevance_score` must be exactly 1.0 (direct keyword match to a Mountain Province municipality). Score 0.4 ("nearby" AI match) is rejected for earthquakes.
- **Non-PHIVOLCS articles**: No `location_relevance_score` threshold is enforced in `process_article_workflow`. The `ai_service.full_analysis` uses `score > 0.2` internally for the "is_relevant" flag, but this does NOT block the article from being marked disaster-related. Articles pass through to summarization as long as `is_disaster_related=True`.
- The `GEOGRAPHIC_PRIORITY` list in `ai_service.py` contains 11 entries: Mountain Province + 10 municipalities.

**`process_article_workflow` creates posts with `APPROVED` status**, not `PENDING_REVIEW`. The admin review step is manual — an admin can approve/reject posts via the dashboard before `publish_approved_posts` picks them up.

## Services (Singletons)

All service instances are module-level singletons:
- `openai_service` — GPT-4o-mini for summarize/caption, DALL-E 3 for images, HuggingFace FLUX.1-schnell as image fallback, source image download (uses separate `IMAGE_API_KEY`/`IMAGE_BASE_URL` if set; falls back to main OpenAI client otherwise)
- `ai_service` — GPT-4o-mini for disaster classification (disasters, accidents, fires, weather), geographic relevance. Has a hardcoded `GEOGRAPHIC_PRIORITY` list (Mountain Province municipalities ONLY).
- `facebook_service` — Meta Graph API (photo post with caption; falls back to text-only if photo fails)
- `phivolcs_service` — USGS earthquake API (filters magnitude ≥ 4.0, haversine proximity ≤ 300km from MP)
- `news_api_service` — NewsAPI + 3 RSS feeds + NewsData.io. Extracts source image URLs. Gracefully skips any source if no key is configured.
- `weather_service` — OpenWeatherMap (current + 5-day forecast for Mountain Province; produces weather alerts when hazardous conditions detected: thunderstorm, rain, wind >15 m/s, heavy rain)

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
- **`MAX_POSTS_PER_HOUR` (default 5) is defined in `config.py` but never referenced by any service code.** The `publish_approved_posts` and `process_pending_articles` tasks process ALL matching rows without LIMIT clauses.

## Admin Auth

- Admin dashboard at `/admin` uses **cookie-based JWT** (not bearer tokens). The `AdminAuthRequired` exception triggers a 303 redirect to `/admin/login`.
- API routes use `OAuth2PasswordBearer` (standard bearer token auth).
- Default admin credentials are seeded at startup from `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars.

## No Test/Lint/Typecheck Config

- No `pytest`, `mypy`, `ruff`, or `pre-commit` configuration exists in this repo.
- If you add any, document the commands here.

## Repo Notes

- `AGENTS.md` is listed in `.gitignore`. If committing it, use `git add -f AGENTS.md`.
- Three Dockerfiles exist: `Dockerfile` (API with `--reload`), `Dockerfile.celery` (Celery worker, concurrency=2), `Dockerfile.beat` (Celery beat scheduler).
- `CELERY_TIMEZONE` is `Asia/Manila` but the Celery beat `enable_utc=True` means UTC is the internal timezone. Beat schedule times in `crontab` are interpreted in Manila time.