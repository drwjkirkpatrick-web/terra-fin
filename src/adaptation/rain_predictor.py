"""RainPredictor — estimates rain likelihood from humidity and temperature trends.

NOTE: This adaptation module combines the latest humidity reading with the
temperature trend (derived from context['trends']) to estimate the chance of
rain in the coming hours. It inherits from AdaptationModule so the
orchestrator, CLI, and dashboard can manage it identically to every other
adaptation module.

Decision rules (evaluated in order, first match wins):
  1. No reading / no humidity metric  → no-data advisory, confidence 0.0
  2. Humidity > 80 % and temp dropping → rain likely,   confidence 0.8 (advisory)
  3. Humidity > 70 % and temp stable   → rain possible, confidence 0.6 (info)
  4. Humidity < 50 %                  → dry, no rain,   confidence 0.7 (info)
  5. Otherwise (ambiguous mid-range)  → stable advisory, confidence 0.3 (info)

WHY: For smallholder farmers without access to weather radar, ambient
humidity and temperature trends are the most accessible rain predictors.
Covering harvest bins before rain prevents crop loss — a timely advisory
delivered a few hours early is worth far more than an accurate forecast that
arrives too late. The thresholds (80 % / 70 % / 50 %) are empirical heuristics
tuned for highland-tropical agronomy where the temp_humidity sensor (SHT40)
provides both metrics.
"""

from __future__ import annotations

import logging
from typing import Any

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Humidity thresholds (percent relative humidity).
HIGH_HUMIDITY_THRESHOLD = 80.0      # rain very likely above this
MODERATE_HUMIDITY_THRESHOLD = 70.0  # rain possible above this
LOW_HUMIDITY_THRESHOLD = 50.0       # dry / no rain below this

# Temperature delta (°C) above which a trend is considered non-zero.
# Deltas within ±TEMP_TREND_THRESHOLD are treated as "stable".
TEMP_TREND_THRESHOLD = 0.1


class RainPredictor(AdaptationModule):
    """Predicts rain likelihood from humidity and temperature trends.

    Class attributes follow the AdaptationModule contract so the framework can
    introspect every adaptation module uniformly (health checks, dashboards,
    recorder).

    The ``analyze`` method reads ``humidity_pct`` and ``temp_c`` from the
    supplied SensorReading's ``metrics`` dict and derives the temperature trend
    direction from ``context['trends']`` (produced by Engine.get_trends).
    """

    name: str = "rain_predictor"
    category: str = "weather"
    description: str = (
        "Predicts rain likelihood from humidity and temperature trends"
    )

    # ------------------------------------------------------------------ #
    # Core analysis
    # ------------------------------------------------------------------ #

    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyze a humidity/temperature reading for rain likelihood.

        Args:
            reading: Latest SensorReading (typically from temp_humidity),
                or None when no data is available.
            context: Orchestrator context dict; ``context['trends']`` may
                contain per-sensor trend dicts with ``temp_c_delta``.

        Returns:
            AdaptationResult with an advisory, confidence, severity, and a
            data dict containing humidity, temp, trend direction, and
            prediction label.
        """
        # --- No reading at all ------------------------------------------- #
        if reading is None:
            return self._result(
                advisory="No humidity data available for rain prediction.",
                confidence=0.0,
                severity="info",
                humidity=None,
                temp=None,
                trend="unknown",
                prediction="no_data",
            )

        metrics: dict[str, float] = reading.metrics
        humidity: float | None = metrics.get("humidity_pct")
        temp: float | None = metrics.get("temp_c")
        trend: str = self._get_temp_trend(context)

        # --- Reading present but no humidity metric ---------------------- #
        if humidity is None:
            return self._result(
                advisory="No humidity data available for rain prediction.",
                confidence=0.0,
                severity="info",
                humidity=None,
                temp=temp,
                trend=trend,
                prediction="no_data",
            )

        # --- High humidity + falling temperature → rain likely ----------- #
        if humidity > HIGH_HUMIDITY_THRESHOLD and trend == "dropping":
            return self._result(
                advisory=(
                    "Rain likely within hours. Consider covering harvest bins."
                ),
                confidence=0.8,
                severity="advisory",
                humidity=humidity,
                temp=temp,
                trend=trend,
                prediction="rain_likely",
            )

        # --- Moderate-high humidity + stable temperature → possible ------ #
        if humidity > MODERATE_HUMIDITY_THRESHOLD and trend == "stable":
            return self._result(
                advisory=(
                    "Humidity rising — rain possible. Monitor sky conditions."
                ),
                confidence=0.6,
                severity="info",
                humidity=humidity,
                temp=temp,
                trend=trend,
                prediction="rain_possible",
            )

        # --- Low humidity → dry, no rain -------------------------------- #
        if humidity < LOW_HUMIDITY_THRESHOLD:
            return self._result(
                advisory="Dry conditions — no rain expected.",
                confidence=0.7,
                severity="info",
                humidity=humidity,
                temp=temp,
                trend=trend,
                prediction="dry",
            )

        # --- Ambiguous mid-range conditions ------------------------------ #
        return self._result(
            advisory="Conditions stable — rain not imminent.",
            confidence=0.3,
            severity="info",
            humidity=humidity,
            temp=temp,
            trend=trend,
            prediction="stable",
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _get_temp_trend(self, context: dict) -> str:
        """Determine the temperature trend direction from context trends.

        The Engine produces a trends dict keyed by sensor name, each value
        being a dict with ``{metric}_delta`` keys. We search for a
        ``temp_c_delta`` entry across all sensor trend dicts. We also accept a
        flat trends dict (``trends['temp_c_delta']``) for convenience in tests
        and simpler contexts.

        Returns one of: "dropping", "rising", "stable", or "unknown" when no
        trend data is available.
        """
        trends: dict[str, Any] = context.get("trends", {})

        # Sensor-keyed structure: {sensor_name: {temp_c_delta: ...}}
        for value in trends.values():
            if isinstance(value, dict) and "temp_c_delta" in value:
                delta = value["temp_c_delta"]
                return self._classify_delta(delta)

        # Flat structure: {temp_c_delta: ...}
        if "temp_c_delta" in trends and isinstance(trends["temp_c_delta"], (int, float)):
            return self._classify_delta(trends["temp_c_delta"])

        return "unknown"

    @staticmethod
    def _classify_delta(delta: float) -> str:
        """Classify a temperature delta into a trend direction."""
        if delta < -TEMP_TREND_THRESHOLD:
            return "dropping"
        if delta > TEMP_TREND_THRESHOLD:
            return "rising"
        return "stable"

    def _result(
        self,
        advisory: str,
        confidence: float,
        severity: str,
        humidity: float | None,
        temp: float | None,
        trend: str,
        prediction: str,
    ) -> AdaptationResult:
        """Build an AdaptationResult with the standard data dict."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "humidity": humidity,
                "temp": temp,
                "trend": trend,
                "prediction": prediction,
            },
            severity=severity,
        )