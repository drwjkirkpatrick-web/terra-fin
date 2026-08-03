"""Evapotranspiration estimation adaptation module for the Terra-Fin agent.

NOTE: This module estimates daily reference evapotranspiration (ET0) from
ambient temperature and relative humidity using a simplified empirical
formula derived from the Hargreaves approach. The classic Hargreaves
equation requires daily min/max temperature and extraterrestrial radiation,
neither of which a single point-in-time reading provides. Because we only
have the current temperature, using temp as both max and min yields
sqrt(0) = 0 — producing zero ET. To avoid this degenerate case, we fall
back to a simpler empirical relationship:

    ET0_mm_day ≈ max(0, (temp_c - 10) * 0.15 * (1 - humidity_pct / 100))

This captures the key drivers: warmer air increases evaporative demand
and lower humidity (a larger vapour-pressure deficit) increases it further.
The (temp_c - 10) term zeroes out ET below ~10 °C, which is broadly
consistent with low evapotranspiration in cool conditions.

This is a ROUGH ESTIMATE. It does not account for solar radiation, wind
speed, crop coefficients, or day length. It is NOT a replacement for a
proper weather station or ET-based irrigation scheduler. Use it as a
quick triage indicator for the orchestrator and dashboard, not as the sole
basis for irrigation decisions.

WHY: In smallholder highland-tropical agriculture (the Terra-Fin context),
irrigation scheduling is often ad-hoc. A timely advisory that says "water
loss is high today — irrigate" or "water loss is minimal — no need yet"
gives the farmer a concrete, actionable signal from sensors that are
already deployed. Pairing the advisory with a severity level lets the
dashboard colour-code the alert and the orchestrator prioritise it against
other modules.
"""


import logging
import math

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ET classification thresholds (mm/day).
# Ordered low → high. Checked most-extreme first so the worst condition is
# reported first, matching the convention used by HumidityComfort.
# ---------------------------------------------------------------------------

HIGH_ET_THRESHOLD = 5.0        # above this → significant water loss, irrigate today
MODERATE_ET_THRESHOLD = 2.0    # above this → schedule irrigation within 1-2 days
LOW_ET_THRESHOLD = 0.5         # above this → normal schedule adequate
# Below LOW_ET_THRESHOLD → minimal loss, no immediate irrigation needed.


class EvapotranspirationEstimator(AdaptationModule):
    """Estimates daily evapotranspiration for irrigation planning.

    NOTE: Reads ``temp_c`` and ``humidity_pct`` from a SensorReading's metrics
    dict and computes a simplified ET0 estimate. The module is stateless
    aside from the base class history, so it is safe to call repeatedly.

    Classification bands (mm/day):
        - > 5.0   : high      — irrigate today            (warning,   conf 0.5)
        - 2.0–5.0 : moderate  — irrigate within 1-2 days  (advisory,  conf 0.5)
        - 0.5–2.0 : low       — normal schedule adequate   (info,      conf 0.4)
        - < 0.5   : minimal   — no immediate irrigation    (info,      conf 0.4)
    """

    name: str = "et_estimator"
    category: str = "weather"
    description: str = "Estimates daily evapotranspiration for irrigation planning"

    # Empirical coefficient for the simplified ET formula.
    # ET0_mm_day ≈ max(0, (temp_c - 10) * ET_COEFFICIENT * (1 - humidity/100))
    ET_COEFFICIENT = 0.15

    def analyze(self, reading, context):
        """Estimate evapotranspiration and return an irrigation advisory.

        Args:
            reading: A SensorReading whose metrics contain ``temp_c`` and
                ``humidity_pct``, or None when no data is available.
            context: Caller-supplied context dict (unused by this module but
                required by the AdaptationModule contract).

        Returns:
            An AdaptationResult with the advisory, confidence, severity, and
            a data dict containing et_mm_day, temp, humidity, and a
            classification label.
        """
        # No reading at all — report the absence honestly.
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No data for ET estimation.",
                confidence=0.0,
                data={
                    "et_mm_day": None,
                    "temp": None,
                    "humidity": None,
                    "classification": "no_data",
                },
                severity="info",
            )

        temp_c = reading.metrics.get("temp_c")
        humidity_pct = reading.metrics.get("humidity_pct")

        # Reading present but required metrics are missing — treat as no data.
        if temp_c is None or humidity_pct is None:
            logger.warning(
                "[%s] reading missing temp_c or humidity_pct: %s",
                self.name,
                reading.metrics,
            )
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No data for ET estimation.",
                confidence=0.0,
                data={
                    "et_mm_day": None,
                    "temp": temp_c,
                    "humidity": humidity_pct,
                    "classification": "no_data",
                },
                severity="info",
            )

        # ------------------------------------------------------------------
        # Simplified empirical ET0 estimate (see module-level docstring for
        # derivation and caveats).
        # ET0_mm_day ≈ max(0, (temp_c - 10) * 0.15 * (1 - humidity/100))
        # ------------------------------------------------------------------
        et_mm_day = max(
            0.0,
            (temp_c - 10.0) * self.ET_COEFFICIENT * (1.0 - humidity_pct / 100.0),
        )
        # Round to 2 decimal places for clean display and comparison.
        et_mm_day = round(et_mm_day, 2)

        # ------------------------------------------------------------------
        # Band classification — checked most-extreme first so the worst
        # condition always wins. See thresholds above.
        # ------------------------------------------------------------------
        if et_mm_day > HIGH_ET_THRESHOLD:
            classification = "high"
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "High evapotranspiration — significant water loss "
                    "expected. Irrigate today."
                ),
                confidence=0.5,
                data={
                    "et_mm_day": et_mm_day,
                    "temp": temp_c,
                    "humidity": humidity_pct,
                    "classification": classification,
                },
                severity="warning",
            )

        if et_mm_day > MODERATE_ET_THRESHOLD:
            classification = "moderate"
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Moderate water loss — schedule irrigation within "
                    "1-2 days."
                ),
                confidence=0.5,
                data={
                    "et_mm_day": et_mm_day,
                    "temp": temp_c,
                    "humidity": humidity_pct,
                    "classification": classification,
                },
                severity="advisory",
            )

        if et_mm_day > LOW_ET_THRESHOLD:
            classification = "low"
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Low water loss — normal irrigation schedule adequate."
                ),
                confidence=0.4,
                data={
                    "et_mm_day": et_mm_day,
                    "temp": temp_c,
                    "humidity": humidity_pct,
                    "classification": classification,
                },
                severity="info",
            )

        # et_mm_day <= 0.5
        classification = "minimal"
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="Minimal water loss — no immediate irrigation needed.",
            confidence=0.4,
            data={
                "et_mm_day": et_mm_day,
                "temp": temp_c,
                "humidity": humidity_pct,
                "classification": classification,
            },
            severity="info",
        )