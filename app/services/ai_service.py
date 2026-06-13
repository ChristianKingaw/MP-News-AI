import json
import logging
from openai import OpenAI
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

GEOGRAPHIC_PRIORITY = [
    "Mountain Province",
    "Bontoc",
    "Sagada",
    "Bauko",
    "Besao",
    "Sabangan",
    "Tadian",
    "Natonin",
    "Paracelis",
    "Barlig",
    "Sadanga",
]


class AIService:
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        self.model = settings.TEXT_MODEL

    async def classify_article(self, title: str, content: str) -> dict:
        try:
            prompt = (
                "You are a disaster and public safety alert classifier for Mountain Province, Philippines. "
                "Analyze this article and return a JSON object with these fields:\n"
                "- relevant: boolean (is this a disaster, public safety incident, or weather alert? Include: "
                "natural disasters, car/road accidents, fires, floods, landslides, typhoons, earthquakes, "
                "power outages, missing persons, rescue operations)\n"
                "- category: string (earthquake, flood, typhoon, landslide, accident, fire, weather, "
                "rescue, power_outage, other)\n"
                "- severity: string (LOW, MEDIUM, HIGH, or CRITICAL)\n"
                "- location: string (affected location, or 'unknown')\n"
                "- confidence: float (0.0 to 1.0)\n\n"
                f"TITLE: {title}\n\nCONTENT: {content[:3000]}"
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You classify disaster and public safety articles. Respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            result_text = response.choices[0].message.content or "{}"
            result = json.loads(result_text)
            return {
                "relevant": result.get("relevant", False),
                "severity": result.get("severity", "LOW").upper(),
                "location": result.get("location", "unknown"),
                "confidence": result.get("confidence", 0.0),
                "category": result.get("category", "other"),
            }
        except Exception as e:
            logger.exception("AI classification failed: %s", e)
            return {
                "relevant": False,
                "severity": "LOW",
                "location": "unknown",
                "confidence": 0.0,
                "category": "other",
            }

    async def assess_geographic_relevance(self, affected_location: str) -> dict:
        location_lower = affected_location.lower()
        score = 0.0
        matched_areas = []

        for area in GEOGRAPHIC_PRIORITY:
            if area.lower() in location_lower:
                score = 1.0
                matched_areas.append(area)
                break

        if not matched_areas and affected_location != "unknown":
            try:
                prompt = (
                    "Determine if the following location is in or near Mountain Province "
                    "or the Cordillera region of the Philippines. Return JSON:\n"
                    "- relevant: boolean\n"
                    "- reason: short string\n\n"
                    f"LOCATION: {affected_location}"
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You determine geographic relevance. Respond with valid JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=100,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )

                result_text = response.choices[0].message.content or "{}"
                result = json.loads(result_text)
                if result.get("relevant", False):
                    score = 0.4
                    matched_areas = ["nearby"]
            except Exception as e:
                logger.exception("Geo relevance AI check failed: %s", e)

        return {
            "is_relevant": score > 0.2,
            "score": round(score, 2),
            "matched_areas": matched_areas,
        }

    async def assess_risk(self, severity: str, location: str, alert_type: str) -> str:
        risk_mapping = {
            "CRITICAL": "critical",
            "HIGH": "high",
            "MEDIUM": "medium",
            "LOW": "low",
        }
        base_risk = risk_mapping.get(severity.upper(), "low")

        mountain_province_keywords = [
            "mountain province", "bontoc", "sagada", "bauko",
            "sabangan", "tadian", "natonin", "paracelis", "barlig",
            "sadanga", "besao",
        ]
        is_local = any(kw in location.lower() for kw in mountain_province_keywords)

        if is_local and base_risk in ("high", "medium"):
            return "critical"
        if is_local and base_risk == "low":
            return "medium"

        return base_risk

    async def extract_location(self, title: str, content: str) -> str | None:
        try:
            prompt = (
                "Extract the primary affected location from this disaster-related article. "
                "Return JSON with a 'location' field. Be specific: municipality and province if possible.\n\n"
                f"TITLE: {title}\n\nCONTENT: {content[:2000]}"
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract geographic location from disaster news. Return valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=100,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            result_text = response.choices[0].message.content or "{}"
            result = json.loads(result_text)
            return result.get("location")
        except Exception as e:
            logger.exception("Location extraction failed: %s", e)
            return None

    async def full_analysis(self, title: str, content: str) -> dict:
        classification = await self.classify_article(title, content)

        if not classification.get("relevant"):
            return {
                "is_disaster_related": False,
                "severity": None,
                "affected_location": None,
                "location_relevance_score": 0.0,
                "risk_level": "low",
            }

        location = classification.get("location", "unknown")

        geo_result = await self.assess_geographic_relevance(location)
        if not geo_result["is_relevant"]:
            ai_location = await self.extract_location(title, content)
            if ai_location:
                location = ai_location
                geo_result = await self.assess_geographic_relevance(location)

        severity = classification.get("severity", "LOW")

        risk_level = await self.assess_risk(severity, location, "general")

        return {
            "is_disaster_related": True,
            "severity": risk_level,
            "affected_location": location,
            "location_relevance_score": geo_result["score"],
            "risk_level": risk_level,
            "classification_confidence": classification.get("confidence", 0.0),
            "category": classification.get("category", "other"),
        }


ai_service = AIService()