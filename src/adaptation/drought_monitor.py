"""Drought monitor adaptation module for the TerraFin agent.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It tracks soil moisture over time, retaining the last 20
readings internally, and computes the average moisture plus a short-term
trend to warn of developing drought conditions before they become critical.

WHY: Soil moisture is the most direct indicator of crop water stress. A
single low reading may be a transient dip, but a sustained downward trend
signals an emerging drought that requires proactive irrigation. By
averaging the last 20 readings the module smooths out sensor noise, while
the 5-reading trend provides an early-warning signal that moisture is
heading in the wrong direction. Pairing the advisory with a confidence and
severity lets the orchestrator prioritise and the dashboard colour-code the
alert.
"""

from __future__ import annotations

import logging
from typing import Any

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class DroughtMonitor(AdaptationModule):
    """Tracks soil moisture trends and warns of developing drought.

    Stores the last 20 soil-moisture readings internally and computes their
    average. The average determines the advisory band and severity, while a
    short-term trend (last 5 readings) appends a "drying" suffix when moisture
    is consistently decreasing.

    Advisory bands (based on average soil moisture):
        - < 15 % : critical — emergency irrigation needed
        - 15–25 %: warning  — increase irrigation frequency
        - 25–35 %: advisory — monitor closely, prepare to irrigate
        - 35–70 %: info     — adequate
        - > 70 % : info     — well-watered, no irrigation needed
    """

    name: str = "drought_monitor"
    category: str = "soil"
    description: str = "Tracks soil moisture trends and warns of developing drought"

    #: Maximum number of readings retained for averaging and trend analysis.
    _MAX_READINGS = 20
    #: Number of recent readings examined for the drying-trend check.
    _TREND_WINDOW = 5

    def __init__(self) -> None:
        super().__init__()
        # Internal store of soil-moisture percentages — last _MAX_READINGS only.
        self._readings: list[float] = []

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyse a soil-moisture reading and return a drought advisory.

        Args:
            reading: A SensorReading whose metrics contain ``soil_moisture_pct``,
                or None when no data is available.
            context: Caller-supplied context dict (unused by this module but
                required by the AdaptationModule contract).

        Returns:
            An AdaptationResult with the advisory, confidence, severity, and
            a data dict containing ``avg_moisture``, ``trend``, and
            ``reading_count``.
        """
        # No reading at all — report the absence honestly.
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil moisture data for drought monitoring.",
                confidence=0.0,
                data={
                    "avg_moisture": None,
                    "trend": "unknown",
                    "reading_count": len(self._readings),
                },
                severity="info",
            )

        moisture = reading.metrics.get("soil_moisture_pct")

        # Reading present but the metric is missing — treat as no data.
        if moisture is None:
            logger.warning(
                "[%s] reading has no soil_moisture_pct metric: %s",
                self.name,
                reading.metrics,
            )
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil moisture data for drought monitoring.",
                confidence=0.0,
                data={
                    "avg_moisture": None,
                    "trend": "unknown",
                    "reading_count": len(self._readings),
                },
                severity="info",
            )

        # Store this reading and trim to the last _MAX_READINGS.
        self._readings.append(float(moisture))
        if len(self._readings) > self._MAX_READINGS:
            self._readings = self._readings[-self._MAX_READINGS:]

        # Compute the average of all retained readings.
        avg_moisture = sum(self._readings) / len(self._readings)

        # Detect a consistently decreasing trend over the last _TREND_WINDOW
        # readings. Each successive reading must be strictly lower than the
        # previous one for the trend to count as "drying".
        trend = self._compute_trend()

        # ------------------------------------------------------------------
        # Band classification — checked most-extreme first so the worst
        # condition always wins.
        # ------------------------------------------------------------------
        if avg_moisture < 15.0:
            advisory = (
                "Severe drought conditions — emergency irrigation needed for all crops."
            )
            confidence = 0.9
            severity = "critical"
        elif avg_moisture < 25.0:
            advisory = "Dry conditions developing — increase irrigation frequency."
            confidence = 0.7
            severity = "warning"
        elif avg_moisture < 35.0:
            advisory = "Soil drying — monitor closely and prepare to irrigate."
            confidence = 0.5
            severity = "advisory"
        elif avg_moisture <= 70.0:
            advisory = "Soil moisture adequate."
            confidence = 0.6
            severity = "info"
        else:
            advisory = "Soil well-watered — no irrigation needed."
            confidence = 0.7
            severity = "info"

        # Append the drying-trend suffix when moisture is consistently
        # declining over the last _TREND_WINDOW readings.
        if trend == "drying":
            advisory += " (trend: drying)"

        data = {
            "avg_moisture": round(avg_moisture, 2),
            "trend": trend,
            "reading_count": len(self._readings),
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
        """Classify the short-term moisture trend.

        Examines the last ``_TREND_WINDOW`` readings. If every successive
        reading is strictly lower than the one before it, the trend is
        ``"drying"``. If every successive reading is strictly higher, the
        trend is ``"wetting"``. Otherwise the trend is ``"stable"``.

        Returns ``"stable"`` when fewer than two readings are available in
        the trend window.
        """
        recent = self._readings[-self._TREND_WINDOW:]
        if len(recent) < 2:
            return "stable"

        all_decreasing = all(
            recent[i] < recent[i - 1] for i in range(1, len(recent))
        )
        if all_decreasing:
            return "drying"

        all_increasing = all(
            recent[i] > recent[i - 1] for i in range(1, len(recent))
        )
        if all_increasing:
            return "wetting"

        return "stable"