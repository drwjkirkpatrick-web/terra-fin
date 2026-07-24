"""Solar radiation adaptation module for the TerraFin agent.

NOTE: This module estimates solar radiation from ambient light-sensor lux
readings using a rough conversion factor (lux × 0.0079 ≈ W/m^2). This is
an *approximation*, not a real pyranometer measurement — the lux-to-W/m^2
ratio varies with light spectrum, sensor response curve, and sky
conditions. Use it for relative plant-growth assessment (daily light
integral trends, shade decisions) rather than for quantitative
energy-balance or PV-yield calculations.

WHY: Most TerraFin deployments carry only a cheap lux sensor (BH1750 or
equivalent), not a dedicated pyranometer. Plant-growth decisions still
need *some* estimate of how much photosynthetically active radiation is
reaching the canopy, so we derive an approximate W/m^2 figure from the
lux reading. The bands below map to actionable advisories: very bright
conditions may warrant shade cloth for tender seedlings, full sun is
optimal for photosynthesis, overcast light slows growth slightly, and
dawn/dusk or night readings tell the farmer that photosynthesis is
minimal or absent. Daily accumulation is tracked internally so a future
extension can expose a daily light integral (DLI) estimate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Lux → W/m^2 conversion and classification thresholds.                       #
# The 0.0079 factor is a rough daylight-to-irradiance approximation; it is    #
# NOT a substitute for a calibrated pyranometer. See the module docstring.     #
# Thresholds are ordered low → high; bands are checked most-extreme first.    #
# --------------------------------------------------------------------------- #

LUX_TO_W_PER_M2 = 0.0079  #: rough conversion factor (daylight, uncalibrated)

VERY_BRIGHT_THRESHOLD = 80_000.0   # lux above this → very high radiation
FULL_SUN_THRESHOLD = 40_000.0      # lux above this → full sun
OVERCAST_THRESHOLD = 10_000.0      # lux above this → overcast / partial sun
DAWN_DUSK_THRESHOLD = 500.0        # lux above this → dawn / dusk
# Below DAWN_DUSK_THRESHOLD → night


class SolarRadiation(AdaptationModule):
    """Estimates solar radiation from light-sensor lux for plant growth.

    Reads ``light_lux`` from a SensorReading's metrics dict, approximates the
    irradiance in W/m^2 (lux × 0.0079), and maps the lux value to one of five
    bands. Each band carries a tailored advisory, a confidence value, and a
    severity level. The module also accumulates daily irradiance internally
    so a future extension can report a daily light integral (DLI) estimate.

    NOTE: The W/m^2 figure is an approximation from lux, not a real
    pyranometer reading. See the module-level docstring for caveats.
    """

    name: str = "solar_radiation"
    category: str = "weather"
    description: str = (
        "Estimates solar radiation from light readings for plant growth "
        "assessment"
    )

    def __init__(self) -> None:
        super().__init__()
        # Daily accumulation tracking — (date_iso, accumulated_w_per_m2).
        # A future extension can surface this as a daily light integral.
        self._daily_accumulation: float = 0.0
        self._accumulation_date: str = ""

    # ------------------------------------------------------------------ #
    # AdaptationModule interface                                          #
    # ------------------------------------------------------------------ #
    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyse a light reading and return a solar-radiation advisory.

        Args:
            reading: A SensorReading whose metrics contain ``light_lux``,
                or None when no data is available.
            context: Caller-supplied context dict (unused by this module
                but required by the AdaptationModule contract).

        Returns:
            An AdaptationResult with advisory, confidence, severity, and a
            data dict containing lux, estimated_w_per_m2, and light_category.
        """
        # No reading at all — report the absence honestly.
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No light data for solar radiation estimate.",
                confidence=0.0,
                data={
                    "lux": None,
                    "estimated_w_per_m2": None,
                    "light_category": "no_data",
                },
                severity="info",
            )

        lux = reading.metrics.get("light_lux")

        # Reading present but the metric is missing — treat as no data.
        if lux is None:
            logger.warning("[%s] reading has no light_lux metric", self.name)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No light data for solar radiation estimate.",
                confidence=0.0,
                data={
                    "lux": None,
                    "estimated_w_per_m2": None,
                    "light_category": "no_data",
                },
                severity="info",
            )

        # Approximate irradiance from lux (uncalibrated — see docstring).
        estimated_w_per_m2 = lux * LUX_TO_W_PER_M2

        # Track daily accumulation. Roll over at a date boundary.
        self._accumulate_daily(estimated_w_per_m2)

        # ------------------------------------------------------------------ #
        # Band classification — checked most-extreme first so the worst       #
        # condition always wins. See module-level thresholds above.          #
        # ------------------------------------------------------------------ #
        if lux > VERY_BRIGHT_THRESHOLD:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    "Very high solar radiation — consider shade cloth for "
                    "sensitive seedlings."
                ),
                confidence=0.6,
                data={
                    "lux": lux,
                    "estimated_w_per_m2": estimated_w_per_m2,
                    "light_category": "very_bright",
                },
                severity="advisory",
            )

        if lux > FULL_SUN_THRESHOLD:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="Optimal solar radiation for photosynthesis.",
                confidence=0.7,
                data={
                    "lux": lux,
                    "estimated_w_per_m2": estimated_w_per_m2,
                    "light_category": "full_sun",
                },
                severity="info",
            )

        if lux > OVERCAST_THRESHOLD:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="Reduced light — growth rate may slow slightly.",
                confidence=0.5,
                data={
                    "lux": lux,
                    "estimated_w_per_m2": estimated_w_per_m2,
                    "light_category": "overcast",
                },
                severity="info",
            )

        if lux > DAWN_DUSK_THRESHOLD:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="Low light — minimal photosynthesis occurring.",
                confidence=0.6,
                data={
                    "lux": lux,
                    "estimated_w_per_m2": estimated_w_per_m2,
                    "light_category": "dawn_dusk",
                },
                severity="info",
            )

        # lux <= 500 → night
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="No solar radiation — night period.",
            confidence=0.8,
            data={
                "lux": lux,
                "estimated_w_per_m2": estimated_w_per_m2,
                "light_category": "night",
            },
            severity="info",
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                    #
    # ------------------------------------------------------------------ #
    def _accumulate_daily(self, w_per_m2: float) -> None:
        """Accumulate irradiance into the running daily total.

        Rolls the accumulator over when the UTC date changes so each day
        starts fresh. This is a simple running sum — a real DLI would
        integrate over time, but this gives a rough relative trend.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._accumulation_date != today:
            self._accumulation_date = today
            self._daily_accumulation = 0.0
        self._daily_accumulation += w_per_m2

    def get_daily_accumulation(self) -> float:
        """Return the accumulated approximate irradiance for the current day."""
        return self._daily_accumulation