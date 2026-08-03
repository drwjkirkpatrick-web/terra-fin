"""Snake alert adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It warns of snake presence likelihood based on air
temperature and ground cover conditions, emitting advisories that range
from 'watch your step' (advisory) to 'low risk' (info).

WHY: Snakes are ectothermic — their activity is tightly coupled to ambient
temperature and ground cover. Warm temperatures (25-35 °C) combined with
sparse ground cover (<40 %) create prime snake foraging conditions. Very
hot temperatures (>35 °C) push snakes into shaded refuges. Cool conditions
(<15 °C) make them sluggish and unlikely to be encountered. By combining a
temperature reading with context-supplied soil temperature and ground-cover
percentage, this module gives the farmer an actionable heads-up before
walking through tall grass, rock piles, or brushy areas.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class SnakeAlert(AdaptationModule):
    """Estimates snake presence likelihood from temperature and ground cover.

    The module pulls air temperature from ``reading.metrics['temp_c']`` and
    enriches it with two context values:

        - ``context['soil_temp_c']`` — ground-level temperature, defaults to
          the air temperature when absent (snakes operate at ground level).
        - ``context['ground_cover_pct']`` — percentage of ground covered by
          vegetation or debris, default 50.

    Advisory bands:
        - temp 25-35 & ground_cover < 40 → advisory, confidence 0.5,
          snake_risk "high"
        - temp 25-35 & ground_cover ≥ 40 → info, confidence 0.4,
          snake_risk "moderate"
        - temp > 35                     → info, confidence 0.4,
          snake_risk "low"
        - temp 15-25                    → info, confidence 0.5,
          snake_risk "low"
        - temp < 15                     → info, confidence 0.6,
          snake_risk "low"
        - no reading                    → info, confidence 0.0,
          snake_risk "low"

    The ``data`` dict always carries:
        - ``temp``          — the temperature used for assessment (°C) or None
        - ``ground_cover``  — ground-cover percentage (int)
        - ``snake_risk``    — one of "high", "moderate", "low"
    """

    name = "snake_alert"
    category = "animal"
    description = "Warns of snake presence likelihood from temperature and ground conditions"

    def analyze(self, reading, context):
        """Evaluate snake risk for a single reading within context.

        Args:
            reading: Current SensorReading whose ``metrics`` may contain
                ``temp_c``. May be None.
            context: Additional context.  Recognised keys:
                ``soil_temp_c`` (float, defaults to air temp),
                ``ground_cover_pct`` (int/float, default 50).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        # Extract air temperature from the reading, if present.
        temp_c = None

        if reading is not None and reading.metrics:
            temp_c = reading.metrics.get("temp_c")

        # Ground cover defaults to 50 % when not supplied.
        ground_cover = context.get("ground_cover_pct", 50)

        # No temperature data at all — cannot assess snake risk.
        if temp_c is None:
            return self._no_data_result(ground_cover)

        # Use soil temp from context when available, otherwise fall back to
        # the air temperature (snakes live at ground level).
        temp = context.get("soil_temp_c", temp_c)

        # Classify snake risk based on temperature and ground cover.
        if temp > 35:
            advisory = (
                "Very hot - snakes seek shade. Check near rocks and dense brush."
            )
            confidence = 0.4
            severity = "info"
            snake_risk = "low"
        elif 25 <= temp <= 35:
            if ground_cover < 40:
                advisory = (
                    "Snake activity likely - warm temps and sparse cover. "
                    "Watch your step and use stick to probe ahead."
                )
                confidence = 0.5
                severity = "advisory"
                snake_risk = "high"
            else:
                advisory = (
                    "Moderate snake risk - warm but adequate cover. "
                    "Stay alert near tall grass."
                )
                confidence = 0.4
                severity = "info"
                snake_risk = "moderate"
        elif 15 <= temp < 25:
            advisory = "Cool conditions - snake activity reduced."
            confidence = 0.5
            severity = "info"
            snake_risk = "low"
        else:  # temp < 15
            advisory = "Too cool for snakes - low risk."
            confidence = 0.6
            severity = "info"
            snake_risk = "low"

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "temp": temp,
                "ground_cover": ground_cover,
                "snake_risk": snake_risk,
            },
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _no_data_result(self, ground_cover):
        """Build the standard 'no temperature data' result."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="No temperature data for snake risk assessment.",
            confidence=0.0,
            data={
                "temp": None,
                "ground_cover": ground_cover,
                "snake_risk": "low",
            },
            severity="info",
        )