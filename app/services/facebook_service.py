import logging
import httpx
from pathlib import Path
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class FacebookService:
    def __init__(self):
        self.page_id = settings.FACEBOOK_PAGE_ID
        self.access_token = settings.FACEBOOK_PAGE_ACCESS_TOKEN
        self.api_version = settings.META_GRAPH_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    async def publish_post(
        self, caption: str, image_path: str | None = None
    ) -> dict[str, str | None]:
        result = {"fb_post_id": None, "fb_post_url": None, "error": None}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                if image_path and Path(image_path).exists():
                    post_id = await self._publish_photo(
                        client, caption, image_path
                    )
                else:
                    post_id = await self._publish_text(client, caption)

                if post_id:
                    result["fb_post_id"] = post_id
                    result["fb_post_url"] = (
                        f"https://facebook.com/{post_id}"
                    )

        except httpx.HTTPError as e:
            logger.error("Facebook API request failed: %s", e)
            result["error"] = str(e)
        except Exception as e:
            logger.exception("Facebook publish failed: %s", e)
            result["error"] = str(e)

        return result

    async def _publish_text(
        self, client: httpx.AsyncClient, caption: str
    ) -> str | None:
        try:
            response = await client.post(
                f"{self.base_url}/{self.page_id}/feed",
                data={
                    "message": caption,
                    "access_token": self.access_token,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("id")
        except Exception as e:
            logger.error("Facebook text post failed: %s", e)
            return None

    async def _publish_photo(
        self, client: httpx.AsyncClient, caption: str, image_path: str
    ) -> str | None:
        try:
            files = {"source": open(image_path, "rb")}
            response = await client.post(
                f"{self.base_url}/{self.page_id}/photos",
                data={
                    "message": caption,
                    "access_token": self.access_token,
                },
                files=files,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("id")
        except Exception as e:
            logger.error("Facebook photo post failed: %s", e)

            return await self._publish_text(client, caption)


facebook_service = FacebookService()