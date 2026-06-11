# Mountain Province Disaster Alert System — Enhanced Architecture

## Overview

An automated disaster alert monitoring, analysis, and Facebook publishing platform for Mountain Province, Philippines.

The system continuously gathers disaster-related information from PHIVOLCS, NewsAPI, and RSS feeds, analyzes relevance using NVIDIA-hosted AI models, generates public advisories and images, stores records in PostgreSQL, and publishes approved content to Facebook through the Meta Graph API.

---

## System Components

### 1. Data Ingestion Layer

#### Sources

| Source       | Service                       | Purpose                     |
| ------------ | ----------------------------- | --------------------------- |
| PHIVOLCS API | `app/services/phivolcs.py`    | Earthquake monitoring       |
| NewsAPI      | `app/services/news_api.py`    | Philippine news monitoring  |
| RSS Feeds    | `app/services/rss_service.py` | Disaster-related news feeds |

Supported RSS feeds:

* PhilStar
* Manila Bulletin
* Inquirer
* CNN Philippines
* PAGASA announcements (optional)

---

### Initial Filtering

Articles pass through:

```text
Keyword Filter
        ↓
AI Relevance Classification
        ↓
Store if Relevant
```

Keyword matching uses:

```env
DISASTER_KEYWORDS
```

Examples:

* earthquake
* landslide
* flood
* typhoon
* wildfire
* evacuation
* heavy rainfall

---

### AI Relevance Classification

NVIDIA-hosted LLM determines:

* Disaster relevance
* Urgency level
* Geographic relevance

Output:

```json
{
  "relevant": true,
  "severity": "HIGH",
  "location": "Mountain Province"
}
```

Only relevant records proceed.

---

### Deduplication

Articles are deduplicated using:

```text
(title, source_url)
```

Additional protection:

```text
content_hash
```

to prevent duplicate Facebook posts.

---

## 2. Backend API (FastAPI)

Entrypoint:

```text
app/main.py
```

Runs on:

```text
localhost:8000
```

### API Modules

#### Health

```http
GET /health
```

#### Alerts

```http
GET    /alerts
POST   /alerts
PATCH  /alerts/{id}
GET    /alerts/{id}
```

#### News

```http
GET    /news
GET    /news/{id}
POST   /news/{id}/process
```

#### Posts

```http
GET    /posts
GET    /posts/{id}
POST   /posts/{id}/approve
POST   /posts/{id}/publish
```

#### Dashboard

```http
GET /dashboard/stats
GET /dashboard/recent-activity
```

#### Admin

```http
/admin
/admin/posts
/admin/news
/admin/alerts
```

---

### Database Session Management

All routes use:

```python
Depends(get_db)
```

Database behavior:

* Auto commit on success
* Auto rollback on failure

Handlers must not call:

```python
session.commit()
```

directly.

---

## 3. Database (PostgreSQL 16)

### Core Tables

#### news_articles

Workflow:

```text
RAW
↓
FILTERED
↓
CLASSIFIED
↓
SUMMARIZED
↓
PUBLISHED
```

or

```text
REJECTED
```

---

#### disaster_alerts

Workflow:

```text
ACTIVE
↓
RESOLVED
↓
ARCHIVED
```

---

#### facebook_posts

Workflow:

```text
DRAFT
↓
PENDING_REVIEW
↓
APPROVED
↓
PUBLISHED
```

or

```text
FAILED
```

---

### Additional Tables

#### audit_logs

Tracks all administrative actions.

Fields:

```text
id
action
entity_type
entity_id
performed_by
created_at
```

Examples:

* Approved Post
* Rejected Article
* Published Alert

---

#### task_logs

Tracks Celery activity.

Fields:

```text
id
task_name
status
started_at
finished_at
error_message
```

---

#### system_settings

Stores configurable values.

Examples:

```text
polling_interval
ai_confidence_threshold
max_publish_count
```

---

## 4. AI Processing Layer (NVIDIA API)

Service:

```text
app/services/ai_service.py
```

### NVIDIA Hosted Models

Responsibilities:

#### Relevance Classification

Determines:

* Disaster relevance
* Location
* Severity

#### Summarization

Produces concise public summaries.

#### Caption Generation

Creates Facebook-ready advisories.

#### Location Extraction

Identifies:

* Municipality
* Province
* Region

#### Risk Assessment

Classifies:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

---

### Image Generation

Image generation is configurable through:

```env
IMAGE_MODEL=
```

Uses the highest-quality image model available through the NVIDIA API deployment.

Images generated:

* Disaster awareness posters
* Emergency advisories
* Earthquake information graphics
* Flood preparedness visuals

Images stored in:

```text
static/images/
```

Served through:

```text
/static
```

---

## 5. Content Processing Workflow

### News Workflow

```text
News Article
      ↓
Keyword Filter
      ↓
AI Classification
      ↓
Location Validation
      ↓
Summarization
      ↓
Caption Generation
      ↓
Optional Image Generation
      ↓
FacebookPost
      ↓
PENDING_REVIEW
```

---

### PHIVOLCS Workflow

```text
PHIVOLCS Earthquake
      ↓
Create Disaster Alert
      ↓
Severity Analysis
      ↓
Caption Generation
      ↓
Optional Image Generation
      ↓
Facebook Post
      ↓
PENDING_REVIEW
```

PHIVOLCS alerts bypass the news workflow.

---

## 6. Geographic Relevance Filtering

Priority locations:

1. Mountain Province
2. Cordillera Administrative Region
3. Northern Luzon
4. National Events

AI extracts:

```text
affected_location
```

Only relevant disasters proceed to publication.

---

## 7. Scheduling and Background Processing

### Celery + Redis

Broker:

```text
CELERY_BROKER_URL
```

Timezone:

```text
Asia/Manila
```

---

### Scheduled Tasks

#### poll_external_sources

Runs every:

```text
POLLING_INTERVAL_MINUTES
```

Responsibilities:

* Fetch PHIVOLCS data
* Fetch NewsAPI articles
* Fetch RSS articles
* Deduplicate records

---

#### process_pending_articles

Runs every:

```text
15 minutes
```

Responsibilities:

* Classification
* Summarization
* Caption generation
* Image generation

---

#### publish_approved_posts

Runs every:

```text
30 minutes
```

Responsibilities:

* Publish up to 5 approved posts

---

### Async Processing

All AI operations run through Celery workers.

FastAPI returns immediately:

```text
POST /news/{id}/process
      ↓
Task Queued
      ↓
202 Accepted
```

Worker performs processing asynchronously.

---

## 8. Publishing Layer

Service:

```text
app/services/facebook_service.py
```

Uses:

```text
Meta Graph API
```

---

### Publishing Flow

Preferred:

```text
Image + Caption
```

Fallback:

```text
Caption Only
```

---

### Retry Mechanism

If publishing fails:

```text
FAILED
↓
Retry #1 (5 min)
↓
Retry #2 (15 min)
↓
Retry #3 (30 min)
```

Fields:

```text
retry_count
last_error
```

stored in database.

---

## 9. Admin Dashboard

Server-rendered Jinja2 interface.

Views:

```text
/admin
/admin/news
/admin/posts
/admin/alerts
/admin/tasks
/admin/audit-logs
```

Capabilities:

* Approve posts
* Reject posts
* Review AI output
* Monitor workers
* View system activity
* Review publishing failures

---

## 10. Security

* JWT authentication
* Password hashing using bcrypt
* Rate limiting
* CSRF protection
* Environment-based secrets
* Role-based access control

Roles:

```text
ADMIN
EDITOR
VIEWER
```

---

## Deployment

Docker Compose services:

* api
* postgres
* redis
* celery_worker
* celery_beat
* nginx (optional)

Startup:

```bash
docker compose up -d
```

---

## End-to-End Workflow

1. Celery polls PHIVOLCS, NewsAPI, and RSS feeds
2. Articles pass keyword filtering
3. NVIDIA AI classifies relevance, severity, and location
4. Relevant content is stored
5. Celery performs summarization and caption generation
6. Optional images are generated
7. Posts enter PENDING_REVIEW
8. Admin reviews content
9. Approved posts are published through Meta Graph API
10. Audit logs record all actions
11. Failed posts automatically retry
