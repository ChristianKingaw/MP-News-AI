import logging
import httpx
from datetime import datetime, timezone
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class PHIVOLCSService:
    def __init__(self):
        self.base_url = settings.EARTHQUAKE_API_URL
        self.keywords = settings.disaster_keywords_list
        self.min_magnitude = 4.0

    async def fetch_earthquake_data(self) -> list[dict]:
        results: list[dict] = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.base_url,
                    params={
                        "format": "geojson",
                        "minmagnitude": self.min_magnitude,
                        "minlatitude": 5.0,
                        "maxlatitude": 21.0,
                        "minlongitude": 116.0,
                        "maxlongitude": 128.0,
                        "orderby": "time",
                        "limit": 50,
                    },
                )
                response.raise_for_status()
                data = response.json()

                for feature in data.get("features", []):
                    props = feature.get("properties", {})
                    geom = feature.get("geometry", {})
                    coords = geom.get("coordinates", [None, None, None])

                    mag = props.get("mag", 0) or 0
                    if float(mag) < self.min_magnitude:
                        continue

                    place = props.get("place", "Unknown location")
                    title = f"M{mag} Earthquake - {place}"
                    content = self._format_earthquake_content(props, coords)

                    results.append({
                        "source_type": "phivolcs",
                        "source_url": props.get("url", ""),
                        "title": title,
                        "content": content,
                        "keywords_matched": "earthquake,lindol",
                        "is_disaster_related": True,
                    })

        except httpx.HTTPError as e:
            logger.error("USGS earthquake API request failed: %s", e)
        except Exception as e:
            logger.exception("Earthquake service error: %s", e)

        return results

    def _format_earthquake_content(self, props: dict, coords: list) -> str:
        parts = []

        place = props.get("place", "Unknown")
        parts.append(f"Location: {place}")

        mag = props.get("mag")
        if mag:
            parts.append(f"Magnitude: {mag}")

        depth = coords[2] if len(coords) > 2 and coords[2] is not None else None
        if depth is not None:
            parts.append(f"Depth: {depth:.1f} km")

        felt = props.get("felt")
        if felt:
            parts.append(f"Felt reports: {felt}")

        tsunami = props.get("tsunami", 0)
        if tsunami:
            parts.append("TSUNAMI WARNING ISSUED")

        alert = props.get("alert")
        if alert and alert != "green":
            parts.append(f"Alert level: {alert}")

        sig = props.get("sig", 0)
        if sig >= 100:
            parts.append(f"Significance: {sig} (high impact)")

        time_ms = props.get("time")
        if time_ms:
            dt = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
            parts.append(f"Time: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        detail_url = props.get("url", "")
        if detail_url:
            parts.append(f"Details: {detail_url}")

        return "\n".join(parts) if parts else "No details available."

    def is_disaster_related(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.keywords)


phivolcs_service = PHIVOLCSService()