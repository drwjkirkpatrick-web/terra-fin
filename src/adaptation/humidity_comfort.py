"""Humidity comfort adaptation module for the Terra-Fin agent.

NOTE: This module assesses ambient relative humidity for two overlapping
concerns: (1) farmer comfort and safety during field work, and (2) plant
stress and fungal-disease risk. High humidity promotes fungal pathogens
(powdery mildew, downy mildew) on leafy greens, while very low humidity
drives rapid transpiration and plant water stress. The thresholds below
are tuned for highland-tropical smallholder agronomy (the Terra-Fin context)
where greens, avocado, and citrus are common crops.

WHY: Humidity is the single most useful leading indicator for fungal
disease outbreaks — it rises hours before visible symptoms appear. A
timely advisory to avoid overhead watering (which raises leaf-surface
wetness duration) or to irrigate during dry spells lets the farmer act
preventively rather than reactively. Pairing the advisory with a
confidence and severity lets the orchestrator prioritise and the
dashboard colour-code the alert.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Humidity thresholds (percent relative humidity).
# Ordered low → high. Checked from most extreme outward so the worst
# condition is reported first.
# ---------------------------------------------------------------------------

VERY_DRY_THRESHOLD = 25.0   # below this → severe plant stress
DRY_THRESHOLD = 40.0        # below this → dry, mulch/irrigate
COMFORTABLE_LOW = 40.0      # comfortable band lower bound
COMFORTABLE_HIGH = 70.0     # comfortable band upper bound
HUMID_THRESHOLD = 85.0      # above this → fungal disease risk high


class HumidityComfort(AdaptationModule):
    """Assesses humidity levels for crop work comfort and plant stress.

    NOTE: Reads ``humidity_pct`` from a SensorReading's metrics dict and maps
    it to one of five bands. Each band carries a tailored advisory, a
    confidence value, and a severity level. The module is stateless aside
    from the base class history, so it is safe to call repeatedly.
    """

    name: str = "humidity_comfort"
    category: str = "weather"
    description: str = (
        "Assesses humidity levels for crop work comfort and plant stress"
    )

    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyse a humidity reading and return a comfort/stress advisory.

        Args:
            reading: A SensorReading whose metrics contain ``humidity_pct``,
                or None when no data is available.
            context: Caller-supplied context dict (unused by this module but
                required by the AdaptationModule contract).

        Returns:
            An AdaptationResult with the advisory, confidence, severity, and
            a data dict containing the humidity value and a comfort_level
            label.
        """
        # No reading at all — report the absence honestly.
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No humidity data.",
                confidence=0.0,
                data={"humidity": None, "comfort_level": "no_data"},
                severity="info",
            )

        humidity = reading.metrics.get("humidity_pct")

        # Reading present but the metric is missing — treat as no data.
        if humidity is None:
            logger.warning("[%s] reading has no humidity_pct metric", self.name)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No humidity data.",
                confidence=0.0,
                data={"humidity": None, "comfort_level": "no_data"},
                severity="info",
            )

        # ------------------------------------------------------------------
        # Band classification — checked most-extreme first so the worst
        # condition always wins. See module-level thresholds above.
        # ------------------------------------------------------------------
        if humidity < VERY_DRY_THRESHOLD:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Very dry — high plant stress risk. Irrigate immediately."
                ),
                confidence=0.8,
                data={"humidity": humidity, "comfort_level": "very_dry"},
                severity="warning",
            )

        if humidity < DRY_THRESHOLD:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Dry air — plants may need extra water. Consider mulching."
                ),
                confidence=0.7,
                data={"humidity": humidity, "comfort_level": "dry"},
                severity="advisory",
            )

        if humidity < COMFORTABLE_HIGH:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="Humidity comfortable for field work.",
                confidence=0.8,
                data={"humidity": humidity, "comfort_level": "comfortable"},
                severity="info",
            )

        if humidity <= HUMID_THRESHOLD:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Humid conditions — monitor for mildew on greens."
                ),
                confidence=0.6,
                data={"humidity": humidity, "comfort_level": "humid"},
                severity="advisory",
            )

        # humidity > 85 %
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=(
                "Very humid — fungal disease risk high. "
                "Avoid overhead watering."
            ),
            confidence=0.7,
            data={"humidity": humidity, "comfort_level": "very_humid"},
            severity="warning",
        )