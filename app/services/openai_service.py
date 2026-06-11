import logging
import base64
import os
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
            organization=settings.OPENAI_ORG_ID or None,
        )
        self.model = "gpt-4o-mini"
        self.image_model = settings.IMAGE_MODEL

    async def summarize_article(self, title: str, content: str) -> str:
        try:
            prompt = (
                "You are a disaster alert assistant for Mountain Province, Philippines. "
                "Summarize the following disaster-related news in 2–3 sentences. "
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
            logger.exception("OpenAI summarization failed: %s", e)
            return ""

    async def generate_caption(
        self, title: str, summary: str, alert_type: str = "general"
    ) -> str:
        try:
            prompt = (
                "You are managing a Facebook page for Mountain Province Disaster Alerts. "
                "Create an engaging, informative Facebook post caption based on the details below. "
                "Include relevant hashtags like #MountainProvince #DisasterAlert. "
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
            logger.exception("OpenAI caption generation failed: %s", e)
            return ""

    async def generate_image(self, prompt: str) -> tuple[str | None, str | None]:
        try:
            response = self.client.images.generate(
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
            logger.exception("OpenAI image generation failed: %s", e)
            return None, None

    async def generate_image_prompt(self, caption: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate concise DALL-E prompts for disaster awareness images. "
                            "Create prompts that are vivid, suitable for news/social media, "
                            "and avoid graphic violence. Focus on safety, preparedness, "
                            "and community resilience. Include 'Philippines mountains landscape' "
                            "context. Keep prompts under 400 characters."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Create a DALL-E image prompt for this disaster alert caption:\n{caption[:500]}",
                    },
                ],
                max_tokens=200,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.exception("Image prompt generation failed: %s", e)
            return ""

    async def _download_image(self, url: str | None) -> str | None:
        if not url:
            return None
        try:
            import httpx

            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                import uuid

                filename = f"disaster_alert_{uuid.uuid4().hex[:12]}.png"
                filepath = STATIC_IMAGES_DIR / filename
                filepath.write_bytes(resp.content)

                return str(filepath)
        except Exception as e:
            logger.exception("OpenAI image download failed: %s", e)
            return None


openai_service = OpenAIService()