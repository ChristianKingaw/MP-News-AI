import logging
import httpx
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class PHIVOLCSService:
    def __init__(self):
        self.base_url = settings.PHIVOLCS_BASE_URL
        self.keywords = settings.disaster_keywords_list

    async def fetch_earthquake_data(self) -> list[dict]:
        results: list[dict] = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/earthquakes",
                    params={"format": "json"},
                )
                response.raise_for_status()
                data = response.json()

                for eq in data if isinstance(data, list) else data.get("items", []):
                    title = eq.get("title", eq.get("location", "Earthquake Alert"))
                    content = self._format_earthquake_content(eq)
                    mag = eq.get("magnitude", 0)

                    try:
                        if float(mag) >= 4.0:
                            results.append({
                                "source_type": "phivolcs",
                                "source_url": eq.get("url", ""),
                                "title": title,
                                "content": content,
                                "keywords_matched": "earthquake,lindol",
                                "is_disaster_related": True,
                            })
                    except (ValueError, TypeError):
                        pass

        except httpx.HTTPError as e:
            logger.error("PHIVOLCS API request failed: %s", e)
        except Exception as e:
            logger.exception("PHIVOLCS service error: %s", e)

        return results

    def _format_earthquake_content(self, eq: dict) -> str:
        parts = []
        if eq.get("title"):
            parts.append(f"Title: {eq['title']}")
        if eq.get("location"):
            parts.append(f"Location: {eq['location']}")
        if eq.get("magnitude"):
            parts.append(f"Magnitude: {eq['magnitude']}")
        if eq.get("depth"):
            parts.append(f"Depth: {eq['depth']} km")
        if eq.get("date_time"):
            parts.append(f"Date/Time: {eq['date_time']}")
        return "\n".join(parts) if parts else "No details available."

    def is_disaster_related(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.keywords)


phivolcs_service = PHIVOLCSService()