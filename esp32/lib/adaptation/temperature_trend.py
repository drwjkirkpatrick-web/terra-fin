"""Temperature trend adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It tracks the last 5 temperature readings internally
and computes the rate of change to warn of rapid shifts that could affect
temperature-sensitive crops.

WHY: Rapid temperature drops can damage or kill sensitive crops, while rapid
rises increase transpiration and water demand. Detecting these trends early
gives the farmer a window to act — harvesting before a cold snap or ensuring
irrigation is ready before heat stress sets in.
"""


import logging
import math

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class TemperatureTrend(AdaptationModule):
    """Tracks temperature changes and warns of rapid shifts.

    Stores the last 5 temperature readings internally and computes the rate
    of change (°C/hour) between the oldest and newest stored readings.

    Thresholds:
        - Dropping faster than 2 °C/hour  → warning (harvest sensitive crops)
        - Rising faster than 3 °C/hour     → advisory (ensure irrigation)
        - Change under 1 °C over window   → info (temperature stable)
    """

    name = "temperature_trend"
    category = "weather"
    description = "Tracks temperature changes and warns of rapid shifts"

    #: Maximum number of readings retained for trend calculation.
    _MAX_READINGS = 5
    #: Thresholds in °C per hour.
    _DROP_WARNING_THRESHOLD = 2.0   # °C/hour, negative rate
    _RISE_ADVISORY_THRESHOLD = 3.0  # °C/hour, positive rate
    _STABLE_THRESHOLD = 1.0         # °C total change over window

    def __init__(self):
        super().__init__()
        # Internal store of (timestamp_iso, temp_c) tuples — last 5 only.
        self._readings: list[tuple[str, float]] = []

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading, context):
        """Analyze a temperature reading and return a trend advisory.

        Args:
            reading: Current SensorReading (may be None).
            context: Additional context dict (unused but required by interface).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No temperature data.",
                confidence=0.0,
                data={
                    "current_temp": None,
                    "trend": "unknown",
                    "rate_of_change": 0.0,
                },
                severity="info",
            )

        temp_c = reading.metrics.get("temp_c")
        if temp_c is None:
            # No temperature metric available — treat as no data.
            logger.warning("[%s] reading has no temp_c metric: %s", self.name, reading.metrics)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No temperature data.",
                confidence=0.0,
                data={
                    "current_temp": None,
                    "trend": "unknown",
                    "rate_of_change": 0.0,
                },
                severity="info",
            )

        # Store this reading and trim to last _MAX_READINGS.
        self._readings.append((reading.timestamp, temp_c))
        if len(self._readings) > self._MAX_READINGS:
            self._readings = self._readings[-self._MAX_READINGS:]

        # Need at least 2 readings to compute a trend.
        if len(self._readings) < 2:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=f"Temperature at {temp_c:.1f}°C — trend pending more readings.",
                confidence=0.0,
                data={
                    "current_temp": temp_c,
                    "trend": "unknown",
                    "rate_of_change": 0.0,
                },
                severity="info",
            )

        # Compute rate of change (°C/hour) from oldest to newest reading.
        oldest_ts, oldest_temp = self._readings[0]
        newest_ts, newest_temp = self._readings[-1]

        rate = self._compute_rate_per_hour(
            oldest_ts, oldest_temp,
            newest_ts, newest_temp,
        )

        trend = self._classify_trend(rate, newest_temp - oldest_temp)

        # Build result based on trend classification.
        if trend == "falling" and abs(rate) > self._DROP_WARNING_THRESHOLD:
            advisory = (
                "Temperature dropping rapidly — consider harvesting "
                "temperature-sensitive crops now."
            )
            confidence = 0.8
            severity = "warning"
        elif trend == "rising" and rate > self._RISE_ADVISORY_THRESHOLD:
            advisory = "Temperature rising rapidly — ensure irrigation is available."
            confidence = 0.7
            severity = "advisory"
        elif trend == "stable":
            advisory = f"Temperature stable at {newest_temp:.1f}°C."
            confidence = 0.5
            severity = "info"
        else:
            # Falling but below the warning threshold, or rising below advisory.
            advisory = (
                f"Temperature at {newest_temp:.1f}°C, "
                f"trend {trend} ({rate:+.1f}°C/hour)."
            )
            confidence = 0.5
            severity = "info"

        data = {
            "current_temp": newest_temp,
            "trend": trend,
            "rate_of_change": round(rate, 2),
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
    def _compute_rate_per_hour(oldest_ts, oldest_temp, newest_ts, newest_temp):
        """Compute rate of change in °C per hour.

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

        delta_temp = newest_temp - oldest_temp
        hours = elapsed_seconds / 3600.0
        return delta_temp / hours if hours != 0 else 0.0

    @staticmethod
    def _classify_trend(rate_per_hour, total_delta):
        """Classify the trend as 'rising', 'falling', or 'stable'.

        Uses the total temperature delta over the window for the stable check,
        and the per-hour rate for rising/falling classification.
        """
        if abs(total_delta) < TemperatureTrend._STABLE_THRESHOLD:
            return "stable"
        if rate_per_hour > 0:
            return "rising"
        return "falling"