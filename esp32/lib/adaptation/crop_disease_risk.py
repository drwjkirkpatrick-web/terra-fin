"""Crop disease risk adaptation module for the Terra-Fin agent.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It estimates fungal crop disease risk from ambient
humidity, temperature, and hours of leaf wetness. Fungal pathogens
(anthracnose, scab, mildew, leaf spot) thrive under warm, humid
conditions and when leaf surfaces stay wet for extended periods.

WHY: Leaf wetness duration is the single strongest predictor of fungal
infection events, but it is rarely measured directly on smallholder
farms. By combining humidity and temperature (always available from a
cheap DHT-style sensor) with an externally-supplied leaf-wetness-hours
estimate, this module gives the farmer an actionable nudge — improve
air circulation, reduce overhead watering, scout for early symptoms —
before an outbreak takes hold. The module is tuned for highland-tropical
agronomy (avocado, citrus, leafy greens) common in the Terra-Fin context.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds (temperature in °C, humidity in % RH, leaf_wetness in hours).
# ---------------------------------------------------------------------------

HUMIDITY_HIGH = 85.0          # above this → high fungal disease risk
HUMIDITY_MODERATE = 70.0      # above this (but <= 85) → moderate risk
LEAF_WETNESS_HIGH = 6.0       # above this → very high disease risk
TEMP_OPTIMAL_LOW = 15.0       # below this → most pathogens inactive
TEMP_OPTIMAL_HIGH = 35.0      # above this → most pathogens inactive
TEMP_WARM_LOW = 20.0          # warm band lower bound for fungal growth
TEMP_WARM_HIGH = 30.0         # warm band upper bound for fungal growth


class CropDiseaseRisk(AdaptationModule):
    """Estimates crop disease risk from humidity, temperature, and leaf wetness.

    Thresholds (temperature in °C, humidity in % RH, leaf_wetness in hours):
        - humidity > 85 and temp 20–30
            → high fungal disease risk (warning, confidence 0.6)
        - humidity > 85 and leaf_wetness_hours > 6
            → very high disease risk (warning, confidence 0.7)
        - humidity 70–85 and temp 20–30
            → moderate disease risk (advisory, confidence 0.5)
        - humidity < 70
            → low fungal disease risk (info, confidence 0.6)
        - temp < 15 or temp > 35
            → temperature outside optimal pathogen range (info, confidence 0.5)
        - no reading
            → no environmental data (confidence 0.0)
    """

    name: str = "crop_disease_risk"
    category: str = "composite"
    description: str = (
        "Estimates crop disease risk from humidity, temperature, and leaf wetness"
    )

    def analyze(self, reading, context):
        """Analyse humidity, temperature, and leaf wetness for disease risk.

        Args:
            reading: A SensorReading whose metrics contain ``humidity_pct``
                and ``temp_c``, or None when no data is available.
            context: Caller-supplied context dict; ``leaf_wetness_hours``
                (float, hours of leaf surface wetness) may be present.

        Returns:
            An AdaptationResult with advisory, confidence, severity, and a
            data dict containing humidity, temp, leaf_wetness_hours, and a
            disease_risk label (high / moderate / low).
        """
        # No reading at all — report the absence honestly.
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No environmental data for disease risk assessment.",
                confidence=0.0,
                data={
                    "humidity": None,
                    "temp": None,
                    "leaf_wetness_hours": context.get("leaf_wetness_hours", 0),
                    "disease_risk": "no_data",
                },
                severity="info",
            )

        humidity = reading.metrics.get("humidity_pct")
        temp = reading.metrics.get("temp_c")
        leaf_wetness_hours = context.get("leaf_wetness_hours", 0)

        # Reading present but either metric missing — treat as no data.
        if humidity is None or temp is None:
            logger.warning(
                "[%s] reading missing temp_c or humidity_pct metric", self.name
            )
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No environmental data for disease risk assessment.",
                confidence=0.0,
                data={
                    "humidity": humidity,
                    "temp": temp,
                    "leaf_wetness_hours": leaf_wetness_hours,
                    "disease_risk": "no_data",
                },
                severity="info",
            )

        # ------------------------------------------------------------------
        # Risk classification — checked most-severe first so the worst
        # condition always wins. See module-level thresholds above.
        # ------------------------------------------------------------------

        # Prolonged leaf wetness overrides everything (very high risk).
        if humidity > HUMIDITY_HIGH and leaf_wetness_hours > LEAF_WETNESS_HIGH:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Prolonged leaf wetness - very high disease risk. "
                    "Improve air circulation and reduce overhead watering."
                ),
                confidence=0.7,
                data={
                    "humidity": humidity,
                    "temp": temp,
                    "leaf_wetness_hours": leaf_wetness_hours,
                    "disease_risk": "high",
                },
                severity="warning",
            )

        # High humidity + warm temperature → high fungal disease risk.
        if (
            humidity > HUMIDITY_HIGH
            and TEMP_WARM_LOW <= temp <= TEMP_WARM_HIGH
        ):
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "High fungal disease risk - humid and warm. "
                    "Anthracnose and scab likely on avocado and citrus."
                ),
                confidence=0.6,
                data={
                    "humidity": humidity,
                    "temp": temp,
                    "leaf_wetness_hours": leaf_wetness_hours,
                    "disease_risk": "high",
                },
                severity="warning",
            )

        # Temperature outside the optimal pathogen range — most pathogens
        # are inactive regardless of humidity.
        if temp < TEMP_OPTIMAL_LOW or temp > TEMP_OPTIMAL_HIGH:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Temperature outside optimal range for most crop pathogens."
                ),
                confidence=0.5,
                data={
                    "humidity": humidity,
                    "temp": temp,
                    "leaf_wetness_hours": leaf_wetness_hours,
                    "disease_risk": "low",
                },
                severity="info",
            )

        # Moderate humidity + warm temperature → moderate disease risk.
        if (
            HUMIDITY_MODERATE < humidity <= HUMIDITY_HIGH
            and TEMP_WARM_LOW <= temp <= TEMP_WARM_HIGH
        ):
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Moderate disease risk - monitor for early signs of "
                    "mildew and leaf spot."
                ),
                confidence=0.5,
                data={
                    "humidity": humidity,
                    "temp": temp,
                    "leaf_wetness_hours": leaf_wetness_hours,
                    "disease_risk": "moderate",
                },
                severity="advisory",
            )

        # Low humidity → low fungal disease risk.
        if humidity < HUMIDITY_MODERATE:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Low fungal disease risk - dry conditions unfavorable "
                    "for most pathogens."
                ),
                confidence=0.6,
                data={
                    "humidity": humidity,
                    "temp": temp,
                    "leaf_wetness_hours": leaf_wetness_hours,
                    "disease_risk": "low",
                },
                severity="info",
            )

        # Fallback: high humidity but temp outside the warm band (and not
        # extreme enough to hit the out-of-range branch above). Report
        # moderate risk so the farmer still gets a heads-up.
        if humidity > HUMIDITY_HIGH:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Humid conditions - monitor for early signs of "
                    "mildew and leaf spot."
                ),
                confidence=0.5,
                data={
                    "humidity": humidity,
                    "temp": temp,
                    "leaf_wetness_hours": leaf_wetness_hours,
                    "disease_risk": "moderate",
                },
                severity="advisory",
            )

        # Default fallback — should not normally be reached.
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="No environmental data for disease risk assessment.",
            confidence=0.0,
            data={
                "humidity": humidity,
                "temp": temp,
                "leaf_wetness_hours": leaf_wetness_hours,
                "disease_risk": "low",
            },
            severity="info",
        )