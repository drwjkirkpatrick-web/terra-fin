"""pH drift tracker adaptation module for the Terra-Fin agent.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It maintains an internal rolling window of the last 20
soil pH readings and compares the newest reading against the window average
to detect slow acidification or alkalinization trends that a single reading
cannot reveal.

WHY: Soil pH drifts gradually — over weeks, not hours — as rainfall leaches
bases, organic matter decomposes, or acidifying fertilisers accumulate. A
single pH reading only tells the farmer the current value; it cannot show
direction. By tracking the trend across readings, this module gives an early
warning before pH leaves the optimal 5.5–7.5 band, letting the farmer apply
lime (to raise pH) or sulphur / acidifying amendments (to lower pH) in time to
protect nutrient availability for the staple crops (maize, beans, greens)
that the Terra-Fin context targets.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Drift thresholds (pH units).
# drift_rate = current_pH - avg_pH over the rolling window.
# A drift magnitude <= DRIFT_STABLE_THRESHOLD is considered noise / stable.
# ---------------------------------------------------------------------------
DRIFT_STABLE_THRESHOLD = 0.1  # pH units; within +/- this band = stable


class PHDriftTracker(AdaptationModule):
    """Monitors pH changes over time to detect soil acidification or
    alkalinization.

    NOTE: Reads ``soil_pH`` from a SensorReading's metrics dict, appends it to
    an internal rolling window of the last 20 readings, and computes
    ``drift_rate = current_pH - avg_pH``. The sign and magnitude of the drift
    rate classify the trend as acidifying, alkalinizing, or stable. With fewer
    than 5 readings the module reports that it is still collecting a baseline
    rather than guessing at a trend.

    WHY: A rolling-window average is robust to single-reading jitter from the
    pH probe, and the 5-reading minimum prevents false trend calls during the
    cold-start period when the window is too short to be meaningful.
    """

    name: str = "ph_drift_tracker"
    category: str = "soil"
    description: str = (
        "Monitors pH changes over time to detect soil acidification or alkalinization"
    )

    #: Maximum number of pH readings retained for drift calculation.
    _MAX_READINGS = 20
    #: Minimum readings required before a drift trend is reported.
    _MIN_READINGS_FOR_DRIFT = 5

    def __init__(self):
        super().__init__()
        # Internal rolling window of pH values — last _MAX_READINGS only.
        self._readings: list[float] = []

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading, context):
        """Analyse a soil pH reading and return a drift-trend advisory.

        Args:
            reading: A SensorReading whose metrics contain ``soil_pH``, or
                None when no data is available.
            context: Caller-supplied context dict (unused by this module but
                required by the AdaptationModule contract).

        Returns:
            An AdaptationResult with the advisory, confidence, severity, and
            a data dict containing ``current_pH``, ``avg_pH``, ``drift_rate``,
            and ``drift_direction``.
        """
        # No reading at all — report the absence honestly.
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No pH data for drift tracking.",
                confidence=0.0,
                data={
                    "current_pH": None,
                    "avg_pH": None,
                    "drift_rate": 0.0,
                    "drift_direction": "no_data",
                },
                severity="info",
            )

        ph = reading.metrics.get("soil_pH")

        # Reading present but the metric is missing — treat as no data.
        if ph is None:
            logger.warning("[%s] reading has no soil_pH metric: %s", self.name, reading.metrics)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No pH data for drift tracking.",
                confidence=0.0,
                data={
                    "current_pH": None,
                    "avg_pH": None,
                    "drift_rate": 0.0,
                    "drift_direction": "no_data",
                },
                severity="info",
            )

        # Store this reading and trim to the last _MAX_READINGS.
        self._readings.append(ph)
        if len(self._readings) > self._MAX_READINGS:
            self._readings = self._readings[-self._MAX_READINGS:]

        # Not enough readings yet to trust a drift estimate.
        if len(self._readings) < self._MIN_READINGS_FOR_DRIFT:
            avg_pH = round(sum(self._readings) / len(self._readings), 2)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="Collecting pH baseline - need more readings for drift analysis.",
                confidence=0.2,
                data={
                    "current_pH": ph,
                    "avg_pH": avg_pH,
                    "drift_rate": 0.0,
                    "drift_direction": "insufficient",
                },
                severity="info",
            )

        # Enough readings — compute the drift of the newest reading relative
        # to the rolling-window average.
        avg_pH = sum(self._readings) / len(self._readings)
        drift_rate = ph - avg_pH
        drift_direction = self._classify_drift(drift_rate)

        if drift_direction == "acidifying":
            advisory = (
                "Soil pH is drifting acidic - consider lime application to raise pH."
            )
            confidence = 0.7
            severity = "warning"
        elif drift_direction == "alkalinizing":
            advisory = (
                "Soil pH is drifting alkaline - consider sulfur or acidifying amendments."
            )
            confidence = 0.7
            severity = "warning"
        else:  # stable
            advisory = f"Soil pH stable at {ph:.1f}."
            confidence = 0.6
            severity = "info"

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "current_pH": ph,
                "avg_pH": round(avg_pH, 2),
                "drift_rate": round(drift_rate, 2),
                "drift_direction": drift_direction,
            },
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_drift(drift_rate):
        """Classify the drift rate as 'acidifying', 'alkalinizing', or 'stable'.

        A drift more negative than -DRIFT_STABLE_THRESHOLD means the current
        pH is below the window average (acidifying); more positive than the
        threshold means alkalinizing; within the band is stable.
        """
        if drift_rate < -DRIFT_STABLE_THRESHOLD:
            return "acidifying"
        if drift_rate > DRIFT_STABLE_THRESHOLD:
            return "alkalinizing"
        return "stable"