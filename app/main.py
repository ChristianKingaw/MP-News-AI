import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import get_settings
from app.database import init_db
from app.api.alerts import router as alerts_router
from app.api.news import router as news_router
from app.api.posts import router as posts_router
from app.api.dashboard import router as dashboard_router
from app.admin.routes import router as admin_router

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path("static")
STATIC_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Mountain Province Disaster Alert System...")
    await init_db()
    logger.info("Database tables initialized")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Mountain Province Disaster Alert System",
    description="Automated disaster alert monitoring and Facebook publishing for Mountain Province, Philippines.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(alerts_router)
app.include_router(news_router)
app.include_router(posts_router)
app.include_router(dashboard_router)
app.include_router(admin_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mp-disaster-alert"}