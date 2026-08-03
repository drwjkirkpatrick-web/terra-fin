"""Frost alert adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It evaluates frost risk from temperature, humidity, and
time-of-day context and emits advisories ranging from 'no risk' (info) to
'frost imminent' (critical).

WHY: Frost is the single most damaging weather event for many crops — a few
degrees below 2 °C overnight can destroy an entire harvest. By combining
temperature with time-of-day awareness (night/early-morning hours carry the
highest risk), this module gives the farmer an actionable window to deploy
covers, wind machines, or sprinklers before damage occurs.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class FrostAlert(AdaptationModule):
    """Warns of frost risk based on temperature, humidity, and time of day.

    Thresholds (temperature in °C):
        - temp < 2                → frost imminent (critical, confidence 0.9)
        - 2 <= temp < 5 (night)   → frost risk (warning, confidence 0.7)
        - 5 <= temp < 10          → cool but above frost threshold (info)
        - temp >= 10              → no frost risk (info)

    Night/early-morning context is supplied via ``context['is_night']`` (bool)
    or ``context['hour']`` (int 0-23).  When ``hour`` falls in 0-6 the module
    treats the period as high-risk regardless of ``is_night``.

    The ``data`` dict always carries:
        - ``temp``         — the temperature reading (°C) or None
        - ``frost_risk``   — one of "imminent", "risk", "none"
        - ``humidity``     — the humidity reading (% RH) or None
        - ``is_night``     — whether night/early-morning context was active
    """

    name = "frost_alert"
    category = "weather"
    description = "Warns of frost risk based on temperature and humidity"

    #: Temperature thresholds in °C.
    _IMMINENT_THRESHOLD = 2.0   # temp below this → frost imminent
    _RISK_THRESHOLD = 5.0       # temp in [2, 5) → risk (if night/early morning)
    _COOL_THRESHOLD = 10.0     # temp in [5, 10) → cool but safe
    #: Early-morning hour window (0-6 inclusive) treated as high-risk.
    _EARLY_MORNING_HOURS = frozenset(range(0, 7))

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading, context):
        """Evaluate frost risk for a single reading.

        Args:
            reading: Current SensorReading (may be None).  Must carry
                ``temp_c`` (and optionally ``humidity_pct``) in ``metrics``.
            context: Additional context.  Recognised keys:
                ``is_night`` (bool), ``hour`` (int 0-23).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        # No reading at all — cannot assess frost risk.
        if reading is None:
            return self._no_data_result()

        temp_c = reading.metrics.get("temp_c")
        if temp_c is None:
            logger.warning("[%s] reading has no temp_c metric: %s", self.name, reading.metrics)
            return self._no_data_result()

        humidity_pct = reading.metrics.get("humidity_pct")

        # Resolve night/early-morning context.
        is_night = bool(context.get("is_night", False))
        hour = context.get("hour")
        if isinstance(hour, int) and hour in self._EARLY_MORNING_HOURS:
            is_night = True

        # Classify frost risk based on temperature + time context.
        if temp_c < self._IMMINENT_THRESHOLD:
            advisory = (
                "Frost imminent — protect sensitive crops immediately with covers."
            )
            confidence = 0.9
            severity = "critical"
            frost_risk = "imminent"
        elif temp_c < self._RISK_THRESHOLD and is_night:
            advisory = "Frost risk — monitor closely. Have covers ready."
            confidence = 0.7
            severity = "warning"
            frost_risk = "risk"
        elif temp_c < self._COOL_THRESHOLD:
            advisory = "Cool but above frost threshold."
            confidence = 0.6
            severity = "info"
            frost_risk = "none"
        else:
            advisory = "No frost risk."
            confidence = 0.8
            severity = "info"
            frost_risk = "none"

        data = {
            "temp": temp_c,
            "frost_risk": frost_risk,
            "humidity": humidity_pct,
            "is_night": is_night,
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
    def _no_data_result(self):
        """Build the standard 'no temperature data' result."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="No temperature data for frost assessment.",
            confidence=0.0,
            data={
                "temp": None,
                "frost_risk": "none",
                "humidity": None,
                "is_night": False,
            },
            severity="info",
        )