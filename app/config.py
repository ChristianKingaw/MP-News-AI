from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    REDIS_URL: str = "redis://redis:6379/0"

    OPENAI_API_KEY: str
    OPENAI_ORG_ID: str = ""

    FACEBOOK_PAGE_ID: str
    FACEBOOK_PAGE_ACCESS_TOKEN: str
    META_GRAPH_API_VERSION: str = "v18.0"

    NEWS_API_KEY: str = ""
    PHIVOLCS_BASE_URL: str = "https://earthquake.phivolcs.dost.gov.ph/api"

    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    SECRET_KEY: str = "changeme"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    POLLING_INTERVAL_MINUTES: int = 60
    MAX_POSTS_PER_HOUR: int = 5

    DISASTER_KEYWORDS: str = "earthquake,flood,typhoon,landslide,volcano,tsunami,storm,tremor,evacuation,bagyo,lindol,baha"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def disaster_keywords_list(self) -> list[str]:
        return [kw.strip().lower() for kw in self.DISASTER_KEYWORDS.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()