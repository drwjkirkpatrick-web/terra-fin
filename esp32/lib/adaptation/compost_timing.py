"""CompostTiming — advises when to turn or apply compost based on soil temp and moisture.

NOTE: Compost decomposition is driven by microbial activity, which depends
heavily on soil temperature and moisture. Below 10 °C microbes are too slow
to break down organic matter efficiently; above 35 °C they begin to stress.
Moisture between 40–60 % keeps the pile aerobic and active — below 30 % the
microbes stall for lack of water, above 70 % the pile goes anaerobic and
nutrients leach away with drainage water.

This module reads ``temp_c`` and ``soil_moisture_pct`` from a SensorReading's
``metrics`` dict and produces a concise advisory telling the farmer whether
to apply now, water first, wait for drainage, or expect slow release.

WHY: Timing compost application to the right soil conditions maximises
nutrient availability and avoids waste. Applying to cold, dry soil wastes
effort — the compost sits inert until conditions improve. Applying to
saturated soil leaches nitrogen and phosphorus into runoff before the
microbes can capture them. A simple temperature × moisture check gives
the smallholder a reliable go/no-go signal without lab tests.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Thresholds (see module docstring for rationale).                            #
# --------------------------------------------------------------------------- #
COLD_TEMP_C = 10.0          # below this, decomposition is very slow
DRY_MOISTURE_PCT = 30.0     # below this, microbes lack water
WET_MOISTURE_PCT = 70.0    # above this, anaerobic / leaching risk
GOOD_TEMP_LOW = 15.0        # good range lower bound
GOOD_TEMP_HIGH = 35.0       # good range upper bound
IDEAL_TEMP_LOW = 20.0       # ideal range lower bound
IDEAL_TEMP_HIGH = 30.0      # ideal range upper bound
GOOD_MOISTURE_LOW = 40.0    # good/ideal moisture lower bound
GOOD_MOISTURE_HIGH = 60.0   # good/ideal moisture upper bound


class CompostTiming(AdaptationModule):
    """Advises when to turn or apply compost based on soil temperature and moisture.

    NOTE: This module is stateless — each ``analyze`` call evaluates the
    current reading independently. It extracts ``temp_c`` and
    ``soil_moisture_pct`` from ``reading.metrics``. When either metric is
    missing, or when the reading itself is ``None``, the module reports that
    it cannot advise.

    Priority of advisories (first match wins):
        1. No reading          → cannot advise.
        2. Moisture < 30 %     → too dry; water first (blocking).
        3. Moisture > 70 %     → too wet; wait for drainage (blocking).
        4. Temp < 10 °C        → too cold; apply but expect slow release.
        5. Temp 20–30 & 40–60  → ideal; apply now for max availability.
        6. Temp 15–35 & 40–60  → good; soil warm and moist, microbes active.
    """

    name: str = "compost_timing"
    category: str = "soil"
    description: str = (
        "Advises when to turn or apply compost based on soil temperature "
        "and moisture"
    )

    # ------------------------------------------------------------------ #
    # Core analysis
    # ------------------------------------------------------------------ #

    def analyze(self, reading, context):
        """Analyze a soil reading and return a compost-timing advisory.

        Args:
            reading: A SensorReading whose ``metrics`` dict may contain
                ``temp_c`` (float, °C) and ``soil_moisture_pct``
                (float, %).  ``None`` is handled gracefully.
            context: Caller-supplied context dict (unused by this module
                but required by the AdaptationModule contract).

        Returns:
            An AdaptationResult whose ``data`` dict always contains
            ``temp``, ``moisture``, ``compost_action``, and
            ``decomposition_rate``.
        """
        # --- No reading → cannot advise --------------------------------- #
        if reading is None:
            return self._result(
                temp=None,
                moisture=None,
                advisory="No data for compost timing.",
                confidence=0.0,
                severity="info",
                compost_action="unknown",
                decomposition_rate="unknown",
            )

        metrics = reading.metrics

        temp = metrics.get("temp_c")

        moisture = metrics.get("soil_moisture_pct")


        # If neither metric is present we can't advise.
        if temp is None and moisture is None:
            return self._result(
                temp=None,
                moisture=None,
                advisory="No data for compost timing.",
                confidence=0.0,
                severity="info",
                compost_action="unknown",
                decomposition_rate="unknown",
            )

        # Coerce to float (metrics are typed as float but be defensive).
        temp_f = float(temp) if temp is not None else None
        moist_f = float(moisture) if moisture is not None else None

        # --- Moisture extremes (blocking) ------------------------------ #
        if moist_f is not None and moist_f < DRY_MOISTURE_PCT:
            return self._result(
                temp=temp_f,
                moisture=moist_f,
                advisory=(
                    "Soil too dry for compost - water before applying to "
                    "activate decomposition."
                ),
                confidence=0.6,
                severity="advisory",
                compost_action="water_then_apply",
                decomposition_rate="stalled",
            )

        if moist_f is not None and moist_f > WET_MOISTURE_PCT:
            return self._result(
                temp=temp_f,
                moisture=moist_f,
                advisory=(
                    "Soil too wet for compost - wait for drainage to avoid "
                    "nutrient leaching."
                ),
                confidence=0.6,
                severity="advisory",
                compost_action="wait",
                decomposition_rate="leaching_risk",
            )

        # --- Too cold --------------------------------------------------- #
        if temp_f is not None and temp_f < COLD_TEMP_C:
            return self._result(
                temp=temp_f,
                moisture=moist_f,
                advisory=(
                    "Too cold for efficient compost decomposition - microbes "
                    "slow. Apply but expect delayed nutrient release."
                ),
                confidence=0.5,
                severity="info",
                compost_action="apply_expect_slow",
                decomposition_rate="slow",
            )

        # --- Ideal subset of good (check first) ------------------------- #
        if (
            temp_f is not None
            and moist_f is not None
            and IDEAL_TEMP_LOW <= temp_f <= IDEAL_TEMP_HIGH
            and GOOD_MOISTURE_LOW <= moist_f <= GOOD_MOISTURE_HIGH
        ):
            return self._result(
                temp=temp_f,
                moisture=moist_f,
                advisory=(
                    "Ideal compost conditions - apply now for maximum "
                    "nutrient availability."
                ),
                confidence=0.7,
                severity="info",
                compost_action="apply_now",
                decomposition_rate="high",
            )

        # --- Good range ------------------------------------------------- #
        if (
            temp_f is not None
            and moist_f is not None
            and GOOD_TEMP_LOW <= temp_f <= GOOD_TEMP_HIGH
            and GOOD_MOISTURE_LOW <= moist_f <= GOOD_MOISTURE_HIGH
        ):
            return self._result(
                temp=temp_f,
                moisture=moist_f,
                advisory=(
                    "Good conditions for compost application - soil warm "
                    "and moist. microbes active."
                ),
                confidence=0.6,
                severity="info",
                compost_action="apply",
                decomposition_rate="moderate",
            )

        # --- Fallback: data present but outside all defined ranges ----- #
        return self._result(
            temp=temp_f,
            moisture=moist_f,
            advisory="No data for compost timing.",
            confidence=0.0,
            severity="info",
            compost_action="unknown",
            decomposition_rate="unknown",
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _result(self, temp, moisture, advisory, confidence, severity, compost_action, decomposition_rate):
        """Build an AdaptationResult with the standard compost data dict."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "temp": temp,
                "moisture": moisture,
                "compost_action": compost_action,
                "decomposition_rate": decomposition_rate,
            },
            severity=severity,
        )