import logging
import httpx
from datetime import datetime, timezone
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

WEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"

MOUNTAIN_PROVINCE_LOCATION = {
    "name": "Mountain Province",
    "lat": settings.WEATHER_LAT,
    "lon": settings.WEATHER_LON,
}


class WeatherService:
    def __init__(self):
        self.api_key = settings.OPENWEATHERMAP_API_KEY

    async def fetch_weather_alerts(self) -> list[dict]:
        results: list[dict] = []

        if not self.api_key:
            logger.info("No OpenWeatherMap API key configured. Skipping weather fetch.")
            return results

        results.extend(await self._fetch_current_weather())
        results.extend(await self._fetch_forecast())

        return results

    async def _fetch_current_weather(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{WEATHER_BASE_URL}/weather",
                    params={
                        "lat": MOUNTAIN_PROVINCE_LOCATION["lat"],
                        "lon": MOUNTAIN_PROVINCE_LOCATION["lon"],
                        "appid": self.api_key,
                        "units": "metric",
                    },
                )
                response.raise_for_status()
                data = response.json()

                weather_list = data.get("weather", [])
                main = data.get("main", {})
                wind = data.get("wind", {})
                clouds = data.get("clouds", {})
                rain = data.get("rain", {})

                condition = weather_list[0].get("main", "") if weather_list else ""
                description = weather_list[0].get("description", "") if weather_list else ""
                temp = main.get("temp", 0)
                humidity = main.get("humidity", 0)
                wind_speed = wind.get("speed", 0)
                cloud_pct = clouds.get("all", 0)

                content_parts = [
                    f"Current Weather for Mountain Province",
                    f"Condition: {description} ({condition})",
                    f"Temperature: {temp}°C",
                    f"Humidity: {humidity}%",
                    f"Wind Speed: {wind_speed} m/s",
                    f"Cloud Cover: {cloud_pct}%",
                ]

                if rain:
                    rain_1h = rain.get("1h", 0) or rain.get("3h", 0)
                    content_parts.append(f"Rainfall (last hour): {rain_1h} mm")

                if self._is_concerning_weather(condition, wind_speed, rain, cloud_pct):
                    content_parts.append(
                        "ALERT: Potentially hazardous weather conditions detected in Mountain Province."
                    )
                    matched = "rain,heavy rain,storm"
                else:
                    matched = "weather"

                return [{
                    "source_type": "weather",
                    "source_url": f"https://openweathermap.org/city/1699757",
                    "title": f"Weather Alert: {description.title()} in Mountain Province"
                        if self._is_concerning_weather(condition, wind_speed, rain, cloud_pct)
                        else f"Mountain Province Weather: {description.title()}, {temp}°C",
                    "content": "\n".join(content_parts),
                    "keywords_matched": matched,
                    "is_disaster_related": self._is_concerning_weather(
                        condition, wind_speed, rain, cloud_pct
                    ),
                    "source_published_at": datetime.now(timezone.utc),
                }]

        except Exception as e:
            logger.exception("Current weather fetch failed: %s", e)
            return []

    async def _fetch_forecast(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{WEATHER_BASE_URL}/forecast",
                    params={
                        "lat": MOUNTAIN_PROVINCE_LOCATION["lat"],
                        "lon": MOUNTAIN_PROVINCE_LOCATION["lon"],
                        "appid": self.api_key,
                        "units": "metric",
                    },
                )
                response.raise_for_status()
                data = response.json()

                results: list[dict] = []
                typhoon_risk = False
                heavy_rain_forecast = False
                max_wind = 0.0
                max_rain = 0.0
                total_rain = 0.0

                for entry in data.get("list", []):
                    wind = entry.get("wind", {})
                    wind_speed = wind.get("speed", 0) or 0
                    rain = entry.get("rain", {})
                    rain_3h = rain.get("3h", 0) or 0
                    total_rain += rain_3h
                    max_wind = max(max_wind, wind_speed)
                    max_rain = max(max_rain, rain_3h)

                if max_wind > 15.0:
                    typhoon_risk = True
                if total_rain > 30.0 or max_rain > 10.0:
                    heavy_rain_forecast = True

                if typhoon_risk or heavy_rain_forecast:
                    content_parts = [
                        "5-Day Weather Forecast for Mountain Province",
                        f"Max Wind Speed: {max_wind:.1f} m/s",
                        f"Total Expected Rainfall: {total_rain:.1f} mm",
                        f"Max 3-Hour Rainfall: {max_rain:.1f} mm",
                    ]

                    if typhoon_risk and max_wind > 25.0:
                        content_parts.append(
                            "WARNING: Strong winds detected — potential typhoon conditions. "
                            "Residents should prepare emergency supplies and monitor official advisories."
                        )
                        matched = "typhoon,storm,bagyo"
                    elif typhoon_risk:
                        content_parts.append(
                            "ADVISORY: Elevated wind speeds in forecast. Monitor conditions closely."
                        )
                        matched = "storm,typhoon,bagyo"
                    elif heavy_rain_forecast:
                        content_parts.append(
                            "ADVISORY: Heavy rainfall expected. Risk of flash floods and landslides "
                            "in Mountain Province. Stay alert and avoid river crossings."
                        )
                        matched = "rain,heavy rain,flood,landslide,baha"
                    else:
                        matched = "weather"

                    results.append({
                        "source_type": "weather",
                        "source_url": "https://openweathermap.org/city/1699757",
                        "title": "Weather Forecast Alert: Potential Hazardous Conditions in Mountain Province"
                            if typhoon_risk
                            else "Weather Forecast: Heavy Rain Expected in Mountain Province",
                        "content": "\n".join(content_parts),
                        "keywords_matched": matched,
                        "is_disaster_related": True,
                        "source_published_at": datetime.now(timezone.utc),
                    })

                return results

        except Exception as e:
            logger.exception("Weather forecast fetch failed: %s", e)
            return []

    def _is_concerning_weather(
        self, condition: str, wind_speed: float, rain: dict, cloud_pct: int
    ) -> bool:
        condition_lower = condition.lower()
        hazardous = {"thunderstorm", "rain", "storm", "snow", "tornado", "squall"}
        if any(h in condition_lower for h in hazardous):
            return True
        if wind_speed > 15.0:
            return True
        if rain and (rain.get("1h", 0) or 0) > 5.0:
            return True
        if rain and (rain.get("3h", 0) or 0) > 10.0:
            return True
        return False


weather_service = WeatherService()