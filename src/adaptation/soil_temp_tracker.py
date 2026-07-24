"""Soil temperature tracker adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It tracks the last 10 soil temperature readings internally
and classifies the current soil temperature into germination/root-health
zones, giving the farmer actionable guidance on planting and crop care.

WHY: Soil temperature governs seed germination and root metabolism far more
directly than air temperature. A warm sunny afternoon can push air temp to
25°C while the soil is still at 8°C — planting then wastes seed because
germination won't occur. Tracking soil temp separately from air temp lets the
farmer time planting to actual root-zone conditions, not the weather above.
"""

from __future__ import annotations

import logging
from typing import Any

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class SoilTempTracker(AdaptationModule):
    """Tracks soil temperature for seed germination and root health.

    The primary source is ``context['soil_temp_c']`` — soil temperature is
    measured separately from air temperature. When that key is absent, the
    module falls back to ``reading.metrics['temp_c']`` (air temp) as a rough
    proxy, logging a warning so the operator knows the value is approximate.

    The last 10 soil-temperature readings are stored internally to compute a
    trend (rising / falling / stable / unknown).

    Temperature zones (°C):
        - < 5     → warning:  too cold, no germination
        - 5–15    → info:     cool, slow germination (cold-tolerant greens OK)
        - 15–25   → info:     optimal for germination and root growth
        - 25–35   → info:     warm, good for tropical crops, watch moisture
        - > 35    → warning:  too hot, root stress, mulch to cool
    """

    name = "soil_temp_tracker"
    category = "soil"
    description = "Tracks soil temperature for seed germination and root health"

    #: Maximum number of readings retained for trend calculation.
    _MAX_READINGS = 10
    #: Minimum readings needed before computing a trend.
    _MIN_READINGS = 2
    #: Total change (°C) below which the trend is considered stable.
    _STABLE_THRESHOLD = 1.0

    def __init__(self) -> None:
        super().__init__()
        # Internal store of (timestamp_iso, soil_temp_c) tuples — last 10 only.
        self._readings: list[tuple[str, float]] = []

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading: SensorReading | None, context: dict) -> AdaptationResult:
        """Analyze soil temperature and return a germination/root-health advisory.

        Args:
            reading: Current SensorReading (may be None if context carries
                soil temp directly).
            context: Additional context dict. ``soil_temp_c`` is the
                preferred source; ``reading.metrics['temp_c']`` is the fallback.

        Returns:
            AdaptationResult with advisory, confidence, severity, and data
            containing ``soil_temp``, ``trend``, and ``germination_outlook``.
        """
        soil_temp = context.get("soil_temp_c", None)
        used_proxy = False

        if soil_temp is None:
            # Fall back to air temp from the reading as a rough proxy.
            if reading is not None:
                soil_temp = reading.metrics.get("temp_c")
                if soil_temp is not None:
                    used_proxy = True
                    logger.info(
                        "[%s] soil_temp_c not in context; using reading.metrics "
                        "temp_c (%.1f°C) as rough proxy",
                        self.name,
                        soil_temp,
                    )

        # --- No soil temperature data at all ---
        if soil_temp is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil temperature data.",
                confidence=0.0,
                data={
                    "soil_temp": None,
                    "trend": "unknown",
                    "germination_outlook": "unknown",
                },
                severity="info",
            )

        # Store this reading and trim to last _MAX_READINGS.
        ts = reading.timestamp if reading is not None else utc_now()
        self._readings.append((ts, soil_temp))
        if len(self._readings) > self._MAX_READINGS:
            self._readings = self._readings[-self._MAX_READINGS:]

        # Compute trend from stored readings.
        trend = self._compute_trend()

        # Classify temperature zone and build advisory.
        if soil_temp < 5:
            advisory = "Soil very cold - no germination expected. Wait for warming."
            confidence = 0.7
            severity = "warning"
            outlook = "none"
        elif soil_temp < 15:
            advisory = (
                "Soil cool - germination slow for most crops. "
                "Cold-tolerant greens may sprout."
            )
            confidence = 0.5
            severity = "info"
            outlook = "slow"
        elif soil_temp < 25:
            advisory = "Soil temperature optimal for germination and root growth."
            confidence = 0.7
            severity = "info"
            outlook = "optimal"
        elif soil_temp < 35:
            advisory = "Soil warm - good for tropical crops. Monitor moisture."
            confidence = 0.5
            severity = "info"
            outlook = "good_tropical"
        else:
            advisory = "Soil too hot - root stress likely. Mulch to cool soil."
            confidence = 0.7
            severity = "warning"
            outlook = "poor_heat_stress"

        data = {
            "soil_temp": soil_temp,
            "trend": trend,
            "germination_outlook": outlook,
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
    def _compute_trend(self) -> str:
        """Classify the trend as 'rising', 'falling', 'stable', or 'unknown'.

        Requires at least _MIN_READINGS stored readings. Uses the total
        delta between the oldest and newest stored reading against the
        stable threshold.
        """
        if len(self._readings) < self._MIN_READINGS:
            return "unknown"

        oldest_temp = self._readings[0][1]
        newest_temp = self._readings[-1][1]
        delta = newest_temp - oldest_temp

        if abs(delta) < self._STABLE_THRESHOLD:
            return "stable"
        if delta > 0:
            return "rising"
        return "falling"