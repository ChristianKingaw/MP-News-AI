# Mountain Province Disaster Alert System — Stack Architecture

## Overview

A five-tier architecture where external data sources (PHIVOLCS, News APIs, and scheduled polling) feed a FastAPI backend. The backend filters and processes information, uses OpenAI services for content generation, stores records in PostgreSQL, and publishes updates to Facebook through the Meta Graph API.

---

## Architecture Flow

### 1. External Data Sources

#### PHIVOLCS
- Provides earthquake alerts and disaster-related information.

#### News API / RSS Feeds
- Provides news articles and updates from Philippine news sources.

#### Celery + Redis
- Runs scheduled tasks.
- Performs hourly polling of external sources.

---

### 2. Backend Layer

#### FastAPI + Python
Responsibilities:
- Receive data from PHIVOLCS and News APIs.
- Filter relevant disaster-related information.
- Orchestrate processing workflows.
- Send content to AI services.
- Manage publication workflow.

---

### 3. Database Layer

#### PostgreSQL
Stores:
- Retrieved news articles
- Generated summaries
- Generated images
- Facebook post logs
- System records and metadata

---

### 4. AI Services

#### OpenAI API
Purpose:
- Summarize disaster-related news
- Generate post captions
- Create readable public alerts

#### OpenAI Image API
Purpose:
- Generate disaster awareness images
- Create visual content accompanying Facebook posts

---

### 5. Publishing Layer

#### Meta Graph API
Requirements:
- Facebook Page Access Token

Responsibilities:
- Receive generated content
- Publish posts to Facebook automatically

#### Facebook Page
Output:
- Disaster alert posts
- AI-generated images
- AI-generated captions and summaries

---

## Optional Components

### Admin Dashboard

Functions:
- Review generated content
- Approve or reject posts
- Monitor system activity
- View publication history

---

## Deployment

### Infrastructure

- Docker Compose
- VPS Hosting or Cloud Server

Deployment stack includes:
- FastAPI application
- PostgreSQL database
- Redis
- Celery workers
- Optional Admin Dashboard

---

## End-to-End Workflow

1. PHIVOLCS and News APIs provide disaster-related information.
2. Celery Scheduler polls data sources hourly.
3. FastAPI receives and filters incoming data.
4. Relevant information is stored in PostgreSQL.
5. OpenAI API generates summaries and captions.
6. OpenAI Image API generates accompanying images.
7. Content may be reviewed through the Admin Dashboard.
8. Meta Graph API publishes approved content.
9. Posts appear on the Facebook Page as disaster alerts.