import logging
from pathlib import Path
from openai import OpenAI
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

STATIC_IMAGES_DIR = Path("static/images")
STATIC_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


class OpenAIService:
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        self.model = settings.TEXT_MODEL
        self.image_model = settings.IMAGE_MODEL

        if self.image_model:
            image_key = settings.IMAGE_API_KEY or settings.OPENAI_API_KEY
            image_base = settings.IMAGE_BASE_URL or "https://api.openai.com/v1"
            self.image_client = OpenAI(
                api_key=image_key,
                base_url=image_base,
            )
        else:
            self.image_client = None

    async def summarize_article(self, title: str, content: str) -> str:
        try:
            prompt = (
                "You are a disaster alert assistant for Mountain Province, Philippines. "
                "Summarize the following disaster-related news in 2-3 sentences. "
                "Use clear and simple language suitable for public alerts. "
                "Include the most critical safety information if available.\n\n"
                f"TITLE: {title}\n\nCONTENT: {content[:3000]}"
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a disaster alert assistant creating concise, accurate public summaries.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0.3,
            )

            return response.choices[0].message.content or ""
        except Exception as e:
            logger.exception("LLM summarization failed: %s", e)
            return ""

    async def generate_caption(
        self, title: str, summary: str, alert_type: str = "general",
        affected_location: str | None = None
    ) -> str:
        try:
            location_note = ""
            if affected_location and affected_location != "unknown":
                location_note = f"The affected area is: {affected_location}. "

            prompt = (
                "You are managing a Facebook page for Mountain Province Disaster Alerts. "
                "Create an engaging, informative Facebook post caption based on the details below. "
                f"{location_note}"
                "IMPORTANT: Only mention Mountain Province if the affected location is actually in Mountain Province. "
                "Do NOT fabricate or assume the location. State the actual affected area as provided. "
                "Include relevant hashtags like #DisasterAlert #MountainProvince (only if applicable). "
                "Keep the tone professional yet approachable.\n\n"
                f"ALERT TYPE: {alert_type}\n"
                f"TITLE: {title}\n"
                f"SUMMARY: {summary}\n\n"
                "Write the Facebook post caption below:"
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a social media manager for a government disaster alert page.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.6,
            )

            return response.choices[0].message.content or ""
        except Exception as e:
            logger.exception("LLM caption generation failed: %s", e)
            return ""

    async def generate_image(self, prompt: str) -> tuple[str | None, str | None]:
        if not self.image_model or not self.image_client:
            logger.info("No image model configured, skipping image generation")
            return None, None

        try:
            response = self.image_client.images.generate(
                model=self.image_model,
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )

            image_url = response.data[0].url
            local_path = await self._download_image(image_url)

            return image_url, local_path
        except Exception as e:
            logger.warning("Image generation failed (will post text-only): %s", e)
            return None, None

    async def generate_image_prompt(self, caption: str) -> str:
        if not self.image_model:
            return ""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate concise image generation prompts for disaster awareness images. "
                            "Create prompts that are vivid, suitable for news/social media, "
                            "and avoid graphic violence. Focus on safety, preparedness, "
                            "and community resilience. Include 'Philippines mountains landscape' "
                            "context. Keep prompts under 400 characters."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Create an image prompt for this disaster alert caption:\n{caption[:500]}",
                    },
                ],
                max_tokens=200,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.warning("Image prompt generation failed: %s", e)
            return ""

    async def download_source_image(self, url: str) -> str | None:
        return await self._download_image(url)

    async def _download_image(self, url: str | None) -> str | None:
        if not url:
            return None
        try:
            import uuid
            import httpx

            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if "jpeg" in content_type or "jpg" in content_type:
                    ext = "jpg"
                elif "png" in content_type:
                    ext = "png"
                elif "webp" in content_type:
                    ext = "webp"
                else:
                    ext = "png"

                filename = f"disaster_alert_{uuid.uuid4().hex[:12]}.{ext}"
                filepath = STATIC_IMAGES_DIR / filename
                filepath.write_bytes(resp.content)

                return str(filepath)
        except Exception as e:
            logger.exception("Image download failed: %s", e)
            return None


openai_service = OpenAIService()