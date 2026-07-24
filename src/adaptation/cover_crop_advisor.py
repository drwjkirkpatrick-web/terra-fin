"""CoverCropAdvisor — recommends cover crop species by season and soil conditions.

NOTE: This adaptation module recommends suitable cover crop species for a
smallholder farm in the Kenyan cropping calendar. It uses the month (from
context) to determine the season — long rains (March–May), short rains
(October–December), or dry season (January–February and June–September) —
and layers soil pH and moisture readings on top of the seasonal
recommendation to flag species that tolerate acidic or very dry conditions.

WHY: Cover crops protect bare soil between cash-crop cycles, suppress weeds,
and — in the case of legumes — fix atmospheric nitrogen for the next planting.
For smallholders without access to extension officers, a simple
season-aware recommendation that also accounts for soil pH and moisture is
often the difference between a cover crop that establishes and one that
fails. The Kenyan bimodal rainfall calendar means the window for
establishing legumes (long rains) and quick-growing covers (short rains) is
short; missing it leaves the soil bare and exposed to erosion.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Seasonal groupings for the Kenyan bimodal rainfall calendar.
# --------------------------------------------------------------------------- #
LONG_RAINS_MONTHS = {3, 4, 5}
SHORT_RAINS_MONTHS = {10, 11, 12}
DRY_MONTHS = {1, 2, 6, 7, 8, 9}

# pH / moisture thresholds that trigger supplemental advisory notes.
ACIDIC_PH_THRESHOLD = 5.5
VERY_DRY_MOISTURE_THRESHOLD = 25.0  # percent


class CoverCropAdvisor(AdaptationModule):
    """Recommends cover crop species based on season, soil pH, and moisture.

    NOTE: This module is **stateless** — it derives its recommendation entirely
    from the current ``context['month']`` and the latest ``SensorReading``
    passed to ``analyze()``. No data is accumulated between calls.

    The module reads ``soil_pH`` and ``soil_moisture_pct`` from the reading's
    ``metrics`` dict (matching the keys produced by the ``soil_ph`` and
    ``soil_moisture`` sensor drivers). When no reading is available the pH and
    moisture supplements are skipped, and when no month is available the module
    reports insufficient data.
    """

    name: str = "cover_crop_advisor"
    category: str = "soil"
    description: str = (
        "Recommends cover crop species based on season, soil pH, and moisture"
    )

    # ------------------------------------------------------------------ #
    # AdaptationModule interface
    # ------------------------------------------------------------------ #

    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyse the month and soil conditions to recommend a cover crop.

        Args:
            reading: A SensorReading whose ``metrics`` may contain
                ``soil_pH`` and ``soil_moisture_pct``, or ``None`` when no
                sensor data is available.
            context: Caller-supplied context dict. ``context['month']`` is
                expected to be an integer 1–12.

        Returns:
            An AdaptationResult whose ``data`` dict contains ``month``,
            ``season``, ``soil_pH``, ``moisture``, and ``recommendation``.
        """
        month: int | None = context.get("month")

        # Extract soil pH and moisture from the reading when present.
        soil_pH: float | None = None
        moisture: float | None = None
        if reading is not None:
            soil_pH = reading.metrics.get("soil_pH")
            moisture = reading.metrics.get("soil_moisture_pct")

        # --- No reading and no month → insufficient data ------------------ #
        if reading is None and month is None:
            return self._result(
                advisory="Insufficient data for cover crop recommendation.",
                confidence=0.0,
                severity="info",
                month=month,
                soil_pH=soil_pH,
                moisture=moisture,
                recommendation="Insufficient data for cover crop recommendation.",
            )

        # --- Determine seasonal recommendation --------------------------- #
        advisory_parts: list[str] = []

        if month in LONG_RAINS_MONTHS:
            season = "long_rains"
            recommendation = (
                "Long rains season - plant legumes (beans, cowpeas) as "
                "cover crop to fix nitrogen."
            )
            advisory_parts.append(recommendation)
            confidence = 0.6
        elif month in SHORT_RAINS_MONTHS:
            season = "short_rains"
            recommendation = (
                "Short rains season - plant quick-growing cover (oats, "
                "vetch) before main crop."
            )
            advisory_parts.append(recommendation)
            confidence = 0.5
        elif month in DRY_MONTHS:
            season = "dry"
            recommendation = (
                "Dry season - consider drought-tolerant cover (sorghum, "
                "lablab) or leave mulch cover."
            )
            advisory_parts.append(recommendation)
            confidence = 0.5
        else:
            # month is None or out of the 1–12 range with no reading.
            season = "unknown"
            recommendation = "Insufficient data for cover crop recommendation."
            advisory_parts.append(recommendation)
            confidence = 0.0

        # --- Supplemental notes based on soil conditions ----------------- #
        if reading is not None and soil_pH is not None and soil_pH < ACIDIC_PH_THRESHOLD:
            advisory_parts.append(
                "Soil acidic - lablab or mucuna can tolerate low pH."
            )

        if (
            reading is not None
            and moisture is not None
            and moisture < VERY_DRY_MOISTURE_THRESHOLD
        ):
            advisory_parts.append(
                "Very dry - select drought-tolerant species only."
            )

        advisory = " ".join(advisory_parts)

        return self._result(
            advisory=advisory,
            confidence=confidence,
            severity="info" if confidence > 0.0 else "info",
            month=month,
            soil_pH=soil_pH,
            moisture=moisture,
            recommendation=recommendation,
            season=season,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _result(
        self,
        advisory: str,
        confidence: float,
        severity: str,
        month: int | None,
        soil_pH: float | None,
        moisture: float | None,
        recommendation: str,
        season: str = "unknown",
    ) -> AdaptationResult:
        """Build an AdaptationResult with the standard data dict."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "month": month,
                "season": season,
                "soil_pH": soil_pH,
                "moisture": moisture,
                "recommendation": recommendation,
            },
            severity=severity,
        )