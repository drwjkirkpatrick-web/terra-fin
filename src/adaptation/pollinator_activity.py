"""Pollinator activity adaptation module for the TerraFin agent.

NOTE: This module estimates pollinator activity from temperature, light, and
wind conditions. Pollinators (bees, butterflies, and other insects) are most
active in warm, bright, calm conditions. Cold temperatures, low light, strong
wind, or excessive heat all reduce pollinator activity, directly affecting
crop yields for flowering plants.

WHY: Pollination is critical for fruit set in many crops (avocado, citrus,
greens). A timely advisory lets the farmer know when pollinators are likely
active so they can plan flowering-window management, avoid pesticide
application during active pollination hours, and calibrate yield
expectations. Pairing the advisory with a confidence and severity lets the
orchestrator prioritise and the dashboard colour-code the alert.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class PollinatorActivity(AdaptationModule):
    """Estimates pollinator activity from temperature, light, and wind.

    NOTE: Reads ``temp_c`` and ``light_lux`` from a SensorReading's metrics dict
    and ``wind_strong`` from the context dict. Each condition band carries a
    tailored advisory, a confidence value, a severity level, and a
    pollination_outlook label (excellent / good / poor). The module is
    stateless aside from the base class history, so it is safe to call
    repeatedly.
    """

    name: str = "pollinator_activity"
    category: str = "animal"
    description: str = (
        "Estimates pollinator activity from temperature, light, and wind"
    )

    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyse temperature, light, and wind to estimate pollinator activity.

        Args:
            reading: A SensorReading whose metrics contain ``temp_c`` and
                ``light_lux``, or None when no data is available.
            context: Caller-supplied context dict. May contain ``wind_strong``
                (bool) indicating strong wind conditions.

        Returns:
            An AdaptationResult with the advisory, confidence, severity, and
            a data dict containing temp, light, wind_strong, and
            pollination_outlook (excellent / good / poor).
        """
        wind_strong = context.get("wind_strong", False)

        # No reading at all — report the absence honestly.
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No data for pollinator activity estimate.",
                confidence=0.0,
                data={
                    "temp": None,
                    "light": None,
                    "wind_strong": wind_strong,
                    "pollination_outlook": "no_data",
                },
                severity="info",
            )

        temp = reading.metrics.get("temp_c")
        light = reading.metrics.get("light_lux")

        # Reading present but required metrics missing — treat as no data.
        if temp is None or light is None:
            logger.warning(
                "[%s] reading missing temp_c or light_lux", self.name
            )
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No data for pollinator activity estimate.",
                confidence=0.0,
                data={
                    "temp": temp,
                    "light": light,
                    "wind_strong": wind_strong,
                    "pollination_outlook": "no_data",
                },
                severity="info",
            )

        # ------------------------------------------------------------------
        # Condition classification — checked most-severe first so the most
        # actionable condition always wins. Wind overrides positive bands
        # because bees avoid flight in strong wind regardless of temperature
        # or light.
        # ------------------------------------------------------------------

        # Strong wind — bees avoid flight; overrides excellent/good.
        if wind_strong:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Wind reducing pollinator activity - bees avoid flight "
                    "in strong wind."
                ),
                confidence=0.5,
                data={
                    "temp": temp,
                    "light": light,
                    "wind_strong": True,
                    "pollination_outlook": "poor",
                },
                severity="advisory",
            )

        # Too hot — bee activity decreases above 35 °C.
        if temp > 35:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Too hot for pollinators - bee activity decreases above "
                    "35C."
                ),
                confidence=0.6,
                data={
                    "temp": temp,
                    "light": light,
                    "wind_strong": False,
                    "pollination_outlook": "poor",
                },
                severity="advisory",
            )

        # Too cold or too dark for most pollinators.
        if temp < 15 or light < 500:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Poor pollination conditions - too cold or dark for most "
                    "pollinators."
                ),
                confidence=0.6,
                data={
                    "temp": temp,
                    "light": light,
                    "wind_strong": False,
                    "pollination_outlook": "poor",
                },
                severity="info",
            )

        # Excellent — warm, bright, and calm.
        if 18 <= temp <= 30 and light > 10000:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Excellent pollination conditions - bees and butterflies "
                    "likely active."
                ),
                confidence=0.7,
                data={
                    "temp": temp,
                    "light": light,
                    "wind_strong": False,
                    "pollination_outlook": "excellent",
                },
                severity="info",
            )

        # Good — adequate temperature and light.
        if 15 <= temp <= 35 and light > 5000:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="Good pollination conditions.",
                confidence=0.5,
                data={
                    "temp": temp,
                    "light": light,
                    "wind_strong": False,
                    "pollination_outlook": "good",
                },
                severity="info",
            )

        # Fallback — conditions do not meet any specific threshold
        # (e.g. temp 15–35 but light between 500 and 5000).
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="Marginal pollination conditions.",
            confidence=0.3,
            data={
                "temp": temp,
                "light": light,
                "wind_strong": False,
                "pollination_outlook": "poor",
            },
            severity="info",
        )