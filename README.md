# Mountain Province Disaster Alert System

Automated disaster alert monitoring and Facebook publishing for Mountain Province, Philippines. The system polls multiple news sources, classifies articles with AI, assesses geographic relevance, and auto-publishes verified alerts to Facebook.

## Architecture

```
News Sources                     Processing Pipeline                Output
┌─────────────┐
│  PHIVOLCS   │──┐
│ (USGS API)  │  │    ┌──────────┐    ┌──────────┐    ┌──────────┐
└─────────────┘  │    │ Keyword  │    │   AI     │    │  Admin   │    ┌──────────┐
                 ├───▶│ Filter & ├───▶│Classify &├───▶│  Review  ├───▶│ Facebook │
┌─────────────┐  │    │ Dedup    │    │Summarize │    │  (Jinja) │    │   Page   │
│  NewsAPI    │──┤    └──────────┘    └──────────┘    └──────────┘    └──────────┘
└─────────────┘  │
                 │
┌─────────────┐  │
│  RSS Feeds  │──┘
│  (4 sources)│
└─────────────┘
```

### Data Flow

1. **Poll** — Celery beat triggers every 60 minutes. Fetches from PHIVOLCS (earthquakes ≥M4.0), NewsAPI, and 4 RSS feeds (PhilStar, Manila Bulletin, CNN Philippines, Inquirer).
2. **Filter & Store** — Articles matched against disaster keywords, deduplicated by title+URL and content hash (SHA-256). Stored in `news_articles` with `FILTERED` status.
3. **Auto-Process** — Every 15 minutes, up to 10 filtered articles are classified by AI (gpt-4o-mini) for disaster relevance and geographic proximity to Mountain Province. Only articles scoring ≥0.2 location relevance proceed to summarization and image generation.
4. **Review** — Posts appear in the admin dashboard with `PENDING_REVIEW` status. Admins approve or reject.
5. **Publish** — Every 30 minutes, up to 5 approved posts are published to Facebook via Meta Graph API. Failed posts are retried up to 3 times before being marked `FAILED`.

### Scheduled Tasks

| Task | Frequency | Description |
|------|-----------|-------------|
| `poll_external_sources` | Every 60 min | Fetches from all news sources |
| `process_pending_articles` | Every 15 min | Classifies and summarizes articles into posts |
| `publish_approved_posts` | Every 30 min | Publishes up to 5 approved posts to Facebook |
| `retry_failed_posts` | Every 10 min | Retries failed posts (up to 3 attempts) |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12, FastAPI (async) |
| Database | PostgreSQL 16, SQLAlchemy 2.0 (async) |
| ORM Driver | asyncpg (app), psycopg2 (Alembic) |
| Task Queue | Celery with Redis broker |
| AI | OpenAI GPT-4o-mini (classification, summarization, captions) |
| Images | DALL-E 3 |
| Admin UI | Jinja2 server-rendered templates, Chart.js dashboard, dark mode |
| Containerization | Docker Compose (5 services) |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- API keys for OpenAI (or NVIDIA NIM), Facebook, and NewsAPI

### Setup

```bash
# 1. Clone and enter the project
git clone <repo-url> && cd MP_AI_Disaster_Alert

# 2. Create environment file from template
cp .env.example .env

# 3. Edit .env with your API keys
#    Required: OPENAI_API_KEY, FACEBOOK_PAGE_ID, FACEBOOK_PAGE_ACCESS_TOKEN
#    Optional: NEWS_API_KEY (RSS feeds work without it)

# 4. Start all services
docker compose up -d
```

### Access

| Service | URL |
|---------|-----|
| API | `http://localhost:8000` |
| Admin Dashboard | `http://localhost:8000/admin` |
| API Docs (Swagger) | `http://localhost:8000/docs` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

Default admin credentials from `.env` (set `ADMIN_USERNAME` and `ADMIN_PASSWORD`).

## Environment Variables

See `.env.example` for all variables. Key ones:

### Required
| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI or NVIDIA NIM API key |
| `FACEBOOK_PAGE_ID` | Facebook page to publish to |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Facebook page access token |

### Optional
| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Use `https://integrate.api.nvidia.com/v1` for NVIDIA NIM |
| `TEXT_MODEL` | `gpt-4o-mini` | Text model for AI tasks |
| `IMAGE_MODEL` | (empty) | Set to `dall-e-3` for image generation, empty to skip |
| `NEWS_API_KEY` | (empty) | NewsAPI key; RSS feeds work without it |
| `POLLING_INTERVAL_MINUTES` | `60` | How often to poll news sources |
| `MAX_POSTS_PER_HOUR` | `5` | Rate limit for Facebook publishing |
| `DISASTER_KEYWORDS` | `earthquake,flood,...` | Comma-separated keywords for filtering |

### NVIDIA NIM (free tier)
To use NVIDIA's free models instead of OpenAI:

```env
OPENAI_API_KEY=nvapi-xxxxxxxxxxxxx
OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
TEXT_MODEL=meta/llama-3.3-70b-instruct
IMAGE_MODEL=                    # Leave empty (NIM doesn't do images)
```

## Project Structure

```
app/
├── main.py                  # FastAPI app, lifespan, exception handlers
├── config.py                # Pydantic settings from .env
├── database.py              # Async engine, session factory, Base, get_db
├── api/                     # REST API routes
│   ├── alerts.py            # Disaster alert endpoints
│   ├── auth.py              # JWT authentication, admin seeding
│   ├── dashboard.py         # Dashboard statistics API
│   ├── news.py              # News article endpoints
│   └── posts.py             # Facebook post endpoints
├── models/                  # SQLAlchemy models (7 tables)
│   ├── alert.py             # DisasterAlert
│   ├── audit.py             # AuditLog
│   ├── base.py              # Convenience re-exports
│   ├── news.py              # NewsArticle + enums
│   ├── post.py              # FacebookPost + enums
│   ├── system_setting.py    # SystemSetting
│   ├── task_log.py          # TaskLog
│   └── user.py              # User + roles
├── schemas/                 # Pydantic request/response schemas
├── services/                # Business logic (singletons)
│   ├── ai_service.py        # GPT-4o-mini classification, geo relevance
│   ├── alert_service.py     # Core pipeline: filter, classify, publish
│   ├── facebook_service.py  # Meta Graph API client
│   ├── news_api.py          # NewsAPI + RSS feed fetcher
│   ├── openai_service.py    # OpenAI summarize, caption, DALL-E 3
│   └── phivolcs.py          # USGS earthquake data fetcher
├── tasks/                   # Celery worker and beat
│   ├── celery_app.py        # Celery instance + beat schedule
│   └── scheduler.py         # Task implementations
└── admin/                   # Admin dashboard (Jinja2)
    ├── routes.py            # Admin page routes + chart API
    └── templates/           # Jinja2 HTML templates (sidebar, dashboard, data tables)
static/
├── css/
│   └── style.css            # Modern CSS: sidebar, dark mode, glassmorphism
└── js/
    └── admin.js             # Vanilla JS: theme toggle, sidebar, Chart.js, toast, dialogs
```

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/token` | Login, returns JWT |
| `GET` | `/auth/me` | Current user info |

### News Articles
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/news` | List articles (paginated) |
| `GET` | `/news/{id}` | Get article detail |
| `POST` | `/news/{id}/process` | Trigger article processing |
| `POST` | `/news/{id}/reject` | Reject an article |

### Facebook Posts
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/posts` | List posts (paginated, filterable by status) |
| `GET` | `/posts/{id}` | Get post detail |
| `POST` | `/posts/{id}/publish` | Publish post to Facebook |
| `POST` | `/posts/{id}/approve` | Approve post for publishing |
| `POST` | `/posts/{id}/reject` | Reject post |

### Disaster Alerts
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/alerts` | List alerts |
| `GET` | `/alerts/{id}` | Get alert detail |
| `POST` | `/alerts` | Create alert |
| `PUT` | `/alerts/{id}` | Update alert |
| `DELETE` | `/alerts/{id}` | Delete alert |

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/dashboard/stats` | Aggregated statistics |

## AI Pipeline Details

### Classification
Articles are classified by GPT-4o-mini for:
- Whether the content is disaster-related
- Severity level (low, medium, high, critical)
- Affected location
- Confidence score (0.0–1.0)

### Geographic Relevance
A two-step process determines relevance to Mountain Province:

1. **Keyword match** — Checks the extracted location against a priority list of 25 municipalities and nearby areas (Bontoc, Sagada, Bauko, Baguio, Benguet, etc.).
2. **AI fallback** — If no keyword match, GPT-4o-mini evaluates whether the location is near Mountain Province.

Only articles with `location_relevance_score ≥ 0.2` advance to summarization.

### Summarization & Publishing
- GPT-4o-mini generates a concise summary and a Facebook-ready caption
- If `IMAGE_MODEL=dall-e-3`, an illustration is generated from the caption
- Post is created with `PENDING_REVIEW` status for admin approval

## News Sources

| Source | Type | Details |
|--------|------|---------|
| USGS Earthquake API | PHIVOLCS | Earthquakes ≥M4.0, free, no API key |
| NewsAPI | News API | Requires `NEWS_API_KEY` |
| PhilStar | RSS Feed | `https://www.philstar.com/rss/headlines` |
| Manila Bulletin | RSS Feed | `https://mb.com.ph/feed` |
| CNN Philippines | RSS Feed | `https://www.cnnphilippines.com/rss.xml` |
| Inquirer | RSS Feed | `https://newsinfo.inquirer.net/feed` |

## Admin Dashboard

The admin dashboard at `/admin` is a modern, glassmorphism-styled Jinja2 server-rendered interface featuring:

- **Sidebar navigation** — Collapsible sidebar with SVG icons, collapsible to icon-only view on desktop, overlay drawer on mobile
- **Dark mode** — Toggle in sidebar footer, persisted to `localStorage`, respects OS `prefers-color-scheme`
- **Glassmorphism** — Backdrop-blur translucent surfaces on cards, modals, toasts, and the sidebar itself
- **Dashboard** — 6 animated stat cards (gradient-accented) plus 3 Chart.js visualizations: alerts by type (bar), post status distribution (donut), articles by source (horizontal bar). Charts auto-redraw on theme toggle
- **News** — Browse and manage news articles
- **Posts** — Approve, reject, or publish Facebook posts (inline actions with confirm dialogs and toast notifications)
- **Alerts** — Manage disaster alerts
- **Tasks** — Celery task execution history
- **Audit Logs** — Admin action audit trail

Authentication is cookie-based JWT. Zero JavaScript frameworks — vanilla JS with Chart.js loaded from CDN on the dashboard only.

## Database

### Models
| Table | Description |
|-------|-------------|
| `news_articles` | Raw articles from all sources with processing status |
| `facebook_posts` | Generated posts linked to articles, with publishing status |
| `disaster_alerts` | Manually created or auto-detected disaster alerts |
| `audit_logs` | Admin action history |
| `task_logs` | Celery task execution records |
| `system_settings` | Key-value configuration store |
| `users` | Admin dashboard users with roles (admin, editor, viewer) |

### Key Behaviors
- UUID primary keys on all tables
- PostgreSQL native ENUM types for status fields
- Deduplication by `(title, source_url)` and `content_hash`
- Alembic configured for migrations (requires `DATABASE_URL_SYNC`)

## Development

### Running Locally (without Docker)
If you prefer running services natively, ensure PostgreSQL 16 and Redis are running, then update `.env`:

```env
POSTGRES_HOST=localhost
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

Then start each service in separate terminals:

```bash
# Terminal 1: API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Celery worker
celery -A app.tasks.celery_app worker --loglevel=info

# Terminal 3: Celery beat (scheduler)
celery -A app.tasks.celery_app beat --loglevel=info
```

### Database Migrations
Alembic is configured but no migrations exist yet. To create the initial migration:

```bash
# Start the services once so tables are created
docker compose up -d

# Generate initial migration
alembic revision --autogenerate -m "init"

# Apply
alembic upgrade head
```

> **Note**: Alembic uses the **sync** URL (`DATABASE_URL_SYNC` with psycopg2), not the async one.

## Docker Services

| Container | Image | Role |
|-----------|-------|------|
| `disaster_db` | `postgres:16-alpine` | PostgreSQL database |
| `disaster_redis` | `redis:7-alpine` | Celery broker and result backend |
| `disaster_api` | Custom `Dockerfile` | FastAPI application with hot-reload |
| `disaster_celery` | Custom `Dockerfile.celery` | Celery worker (concurrency=2) |
| `disaster_beat` | Custom `Dockerfile.beat` | Celery beat scheduler |

### Volumes
| Volume | Purpose |
|--------|---------|
| `pgdata` | PostgreSQL data persistence |
| `redisdata` | Redis data persistence |
| `generated_images` | DALL-E 3 generated images (`/app/static/images`) |

## Troubleshooting

### API won't start
Check that `.env` uses Docker service names, not `localhost`:
```env
POSTGRES_HOST=db          # NOT localhost
REDIS_URL=redis://redis:6379/0   # NOT localhost
```

### Admin login redirects to login page
After entering credentials, check the browser accepts cookies. The admin uses cookie-based JWT authentication.

### Facebook publishing fails
Verify `FACEBOOK_PAGE_ACCESS_TOKEN` is a **page** access token (not a user token). Generate one via the Facebook Graph API Explorer with `pages_manage_posts` and `pages_read_engagement` permissions.

### Celery tasks not running
Ensure both `disaster_celery` (worker) and `disaster_beat` (scheduler) containers are running:
```bash
docker compose ps
```