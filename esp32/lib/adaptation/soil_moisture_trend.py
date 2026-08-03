"""Soil moisture trend adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It tracks the last 10 soil moisture readings internally
and computes the rate of change to predict when irrigation will be needed,
giving the farmer a proactive rather than reactive irrigation window.

WHY: Soil moisture degrades continuously between readings. A simple
threshold ("water when below 30%") only fires after the crop is already
stressed. By computing the rate of change we can project forward — if
moisture is dropping at 3%/hour and currently at 45%, the farmer knows
irrigation is needed within hours, not when the soil is already dry.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class SoilMoistureTrend(AdaptationModule):
    """Tracks soil moisture rate of change to predict irrigation timing.

    Stores the last 10 soil moisture readings internally and computes the
    rate of change (%/hour) between the oldest and newest stored readings.

    Thresholds (%/hour):
        - rate < -2.0   → warning: dropping fast, irrigate within hours
        - rate < -0.5   → advisory: slowly drying, plan irrigation in 1-2 days
        - |rate| ≤ 0.5  → info: stable
        - rate > 0.5    → info: increasing, skip irrigation
    """

    name = "soil_moisture_trend"
    category = "soil"
    description = "Tracks soil moisture rate of change to predict irrigation timing"

    #: Maximum number of readings retained for trend calculation.
    _MAX_READINGS = 10
    #: Minimum readings needed before computing a trend.
    _MIN_READINGS = 3
    #: Thresholds in % per hour.
    _DROP_FAST_THRESHOLD = -2.0   # %/hour — dropping fast
    _DRYING_THRESHOLD = -0.5       # %/hour — slowly drying
    _STABLE_THRESHOLD = 0.5        # %/hour — |rate| at or below this is stable

    def __init__(self):
        super().__init__()
        # Internal store of (timestamp_iso, moisture_pct) tuples — last 10 only.
        self._readings: list[tuple[str, float]] = []

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading, context):
        """Analyze a soil moisture reading and return a trend advisory.

        Args:
            reading: Current SensorReading (may be None).
            context: Additional context dict (unused but required by interface).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        # --- No reading at all ---
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil moisture data.",
                confidence=0.0,
                data={
                    "current_moisture": None,
                    "rate_of_change": 0.0,
                    "trend_direction": "unknown",
                },
                severity="info",
            )

        moisture = reading.metrics.get("soil_moisture_pct")
        if moisture is None:
            # No soil moisture metric available — treat as no data.
            logger.warning(
                "[%s] reading has no soil_moisture_pct metric: %s",
                self.name,
                reading.metrics,
            )
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil moisture data.",
                confidence=0.0,
                data={
                    "current_moisture": None,
                    "rate_of_change": 0.0,
                    "trend_direction": "unknown",
                },
                severity="info",
            )

        # Store this reading and trim to last _MAX_READINGS.
        self._readings.append((reading.timestamp, moisture))
        if len(self._readings) > self._MAX_READINGS:
            self._readings = self._readings[-self._MAX_READINGS:]

        # Need at least _MIN_READINGS to compute a trend.
        if len(self._readings) < self._MIN_READINGS:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="Collecting baseline data - need more readings for trend.",
                confidence=0.2,
                data={
                    "current_moisture": moisture,
                    "rate_of_change": 0.0,
                    "trend_direction": "unknown",
                },
                severity="info",
            )

        # Compute rate of change (%/hour) from oldest to newest reading.
        oldest_ts, oldest_moisture = self._readings[0]
        newest_ts, newest_moisture = self._readings[-1]

        rate = self._compute_rate_per_hour(
            oldest_ts, oldest_moisture,
            newest_ts, newest_moisture,
        )

        # Classify trend and build advisory.
        if rate < self._DROP_FAST_THRESHOLD:
            advisory = "Soil moisture dropping rapidly - irrigate within hours."
            confidence = 0.8
            severity = "warning"
            trend_direction = "dropping_fast"
        elif rate < self._DRYING_THRESHOLD:
            advisory = "Soil slowly drying - plan irrigation within 1-2 days."
            confidence = 0.6
            severity = "advisory"
            trend_direction = "drying"
        elif rate <= self._STABLE_THRESHOLD:
            advisory = f"Soil moisture stable at {newest_moisture:.1f}%."
            confidence = 0.5
            severity = "info"
            trend_direction = "stable"
        else:
            advisory = "Soil moisture increasing - skip irrigation."
            confidence = 0.6
            severity = "info"
            trend_direction = "increasing"

        data = {
            "current_moisture": newest_moisture,
            "rate_of_change": round(rate, 2),
            "trend_direction": trend_direction,
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
    @staticmethod
    def _compute_rate_per_hour(oldest_ts, oldest_moisture, newest_ts, newest_moisture):
        """Compute rate of change in % per hour.

        Returns 0.0 if the timestamps cannot be parsed or span zero time.
        """
        from core.types import parse_iso

        try:
            t_old = parse_iso(oldest_ts)
            t_new = parse_iso(newest_ts)
        except Exception:
            logger.warning("Could not parse timestamps for rate calculation")
            return 0.0

        elapsed_seconds = (t_new - t_old).total_seconds()
        if elapsed_seconds == 0:
            return 0.0

        delta_moisture = newest_moisture - oldest_moisture
        hours = elapsed_seconds / 3600.0
        return delta_moisture / hours if hours != 0 else 0.0