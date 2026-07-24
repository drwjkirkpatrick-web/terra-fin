"""Pest pressure adaptation module for the TerraFin agent.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It tracks pest activity likelihood based on temperature,
humidity, and seasonal context, then emits advisories tuned for common Kenyan
orchard pests: fruit flies (warm + wet), aphids (moderate temp + high
humidity), and thrips (hot + dry).

WHY: Insect pressure is strongly weather-driven. A few days of warm, humid
conditions can trigger a fruit-fly explosion that ruins a citrus or mango
harvest, while hot dry spells bring thrips that silver the fruit surface. By
mapping temperature/humidity bands to the pests those conditions favour, this
module gives the farmer an early, actionable nudge — check traps, inspect new
growth, harvest promptly — before visible damage accumulates. Seasonal
context (month) is carried through so the orchestrator and dashboard can
correlate advisories with the Kenyan bimodal rainy season.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class PestPressure(AdaptationModule):
    """Tracks pest activity from temperature, humidity, and seasonal context.

    Thresholds (temperature in °C, humidity in % RH):
        - 25 <= temp <= 35 and humidity > 60
            → fruit fly activity likely (warning, confidence 0.6)
        - 20 <= temp <= 30 and humidity > 70
            → aphid pressure high (advisory, confidence 0.5)
        - temp > 30 and humidity < 40
            → thrips activity likely (advisory, confidence 0.5)
        - 15 <= temp <= 25 and 40 <= humidity <= 70
            → moderate pest pressure (info, confidence 0.4)
        - temp < 15
            → low pest pressure (info, confidence 0.5)

    Bands are checked in the order above so the most acute condition wins
    (e.g. warm+wet is reported as a fruit-fly warning before the overlapping
    aphid band). Anything outside every band falls through to a routine
    "monitor" advisory.

    The ``data`` dict always carries:
        - ``temp``        — the temperature reading (°C) or None
        - ``humidity``    — the humidity reading (% RH) or None
        - ``pest_risks``  — list of likely pest identifiers (e.g. ``["fruit_flies"]``)
        - ``month``       — the month from context (1-12), defaulting to 1
    """

    name: str = "pest_pressure"
    category: str = "insect"
    description: str = (
        "Tracks pest activity based on temperature, humidity, and seasonal patterns"
    )

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Assess pest pressure for a single reading.

        Args:
            reading: Current SensorReading (may be None). Must carry
                ``temp_c`` and ``humidity_pct`` in ``metrics``.
            context: Additional context. Recognised key:
                ``month`` (int 1-12, defaults to 1).

        Returns:
            An AdaptationResult with advisory, confidence, severity, and a
            data dict containing temp, humidity, pest_risks, and month.
        """
        month = context.get("month", 1)

        # No reading at all — cannot assess pest pressure.
        if reading is None:
            return self._no_data_result(month)

        temp_c = reading.metrics.get("temp_c")
        humidity_pct = reading.metrics.get("humidity_pct")

        # Reading present but either required metric is missing.
        if temp_c is None or humidity_pct is None:
            logger.warning(
                "[%s] reading missing temp_c or humidity_pct: %s",
                self.name,
                reading.metrics,
            )
            return self._no_data_result(month)

        # ------------------------------------------------------------------
        # Band classification — checked most acute first so the worst
        # condition always wins. See class docstring for the threshold map.
        # ------------------------------------------------------------------
        if 25 <= temp_c <= 35 and humidity_pct > 60:
            advisory = (
                "Fruit fly activity likely - warm and humid conditions. "
                "Check traps and harvest promptly."
            )
            confidence = 0.6
            severity = "warning"
            pest_risks = ["fruit_flies"]
        elif 20 <= temp_c <= 30 and humidity_pct > 70:
            advisory = (
                "Aphid pressure high - humid moderate temps favor aphids. "
                "Check new growth on citrus."
            )
            confidence = 0.5
            severity = "advisory"
            pest_risks = ["aphids"]
        elif temp_c > 30 and humidity_pct < 40:
            advisory = (
                "Thrips activity likely - hot dry conditions. "
                "Check for silvering on fruit."
            )
            confidence = 0.5
            severity = "advisory"
            pest_risks = ["thrips"]
        elif 15 <= temp_c <= 25 and 40 <= humidity_pct <= 70:
            advisory = (
                "Moderate pest pressure - conditions not ideal for major outbreaks."
            )
            confidence = 0.4
            severity = "info"
            pest_risks = []
        elif temp_c < 15:
            advisory = (
                "Low pest pressure - cool temperatures suppress insect activity."
            )
            confidence = 0.5
            severity = "info"
            pest_risks = []
        else:
            # Conditions outside every specific band — routine monitoring.
            advisory = (
                "Pest pressure uncertain - conditions outside typical outbreak "
                "ranges. Monitor routinely."
            )
            confidence = 0.3
            severity = "info"
            pest_risks = []

        data = {
            "temp": temp_c,
            "humidity": humidity_pct,
            "pest_risks": pest_risks,
            "month": month,
        }

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data=data,
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _no_data_result(self, month: int = 1) -> AdaptationResult:
        """Build the standard 'no environmental data' result."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="No environmental data for pest assessment.",
            confidence=0.0,
            data={
                "temp": None,
                "humidity": None,
                "pest_risks": [],
                "month": month,
            },
            severity="info",
        )