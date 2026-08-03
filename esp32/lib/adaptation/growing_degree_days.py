"""Growing degree days (GDD) accumulation adaptation module.

NOTE: This module accumulates growing degree days (GDD) from temperature
readings to track crop development timing. GDD is a heat-unit measure used
worldwide in agronomy: each crop has a base temperature below which growth
effectively stops, and the cumulative heat units above that base determine
when the crop reaches key phenological stages (emergence, flowering,
maturity, harvest).

WHY: Knowing accumulated GDD lets a farmer predict harvest windows, plan
planting dates, and compare season-to-season development pace without relying
on calendar dates alone — a critical advantage in highland-tropical
smallholder contexts where microclimate variation shifts the growing season
by weeks between nearby plots.

APPROXIMATION: The standard GDD formula uses daily max and min temperatures:
    GDD_day = max(0, (T_max + T_min) / 2 - T_base)
Terra-Fin sensors typically provide a single instantaneous temperature, not
a full daily max/min pair. This module therefore approximates each day's GDD
using the current reading as a proxy for both max and min:
    GDD_day ≈ max(0, T_current - T_base)
This **overestimates** GDD on days with wide diurnal swings (hot midday
readings) and **underestimates** it when the reading happens during a cool
morning. The approximation is documented here so downstream consumers know
the uncertainty. When true daily max/min data becomes available, the formula
should be upgraded accordingly.

The base temperature used is 10 °C, a common default for many cereals,
vegetables, and tree crops (maize, tomatoes, beans, citrus). Crop-specific
modules can subclass and override ``BASE_TEMP`` for tighter accuracy.
"""
try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

def _make_lock():
    if hasattr(thread_mod, "allocate_lock"):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()



import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Season-stage thresholds (cumulative GDD).
# These are generalised bands; individual crops have their own degree-day
# requirements, but these ranges give useful coarse guidance for a mixed
# smallholder plot.
# --------------------------------------------------------------------------- #
EARLY_SEASON_LIMIT = 100      # < 100 → early development
MID_SEASON_LIMIT = 500        # 100–500 → active vegetative growth
PEAK_SEASON_LIMIT = 1500      # 500–1500 → approaching maturity
# > 1500 → late season, harvest approaching


class GrowingDegreeDays(AdaptationModule):
    """Accumulates growing degree days (GDD) from temperature readings.

    Each call to :meth:`analyze` with a valid temperature reading adds that
    reading's contribution to the internal ``_gdd_total`` accumulator and
    returns an advisory describing the current seasonal stage.

    Thread-safety: accumulation is guarded by a re-entrant lock so the
    module can be polled concurrently by the orchestrator.
    """

    name: str = "growing_degree_days"
    category: str = "weather"
    description: str = (
        "Tracks accumulated growing degree days for crop development timing"
    )

    #: Base temperature (°C) below which growth is assumed to stall.
    BASE_TEMP: float = 10.0

    def __init__(self):
        super().__init__()
        # Cumulative GDD accumulator — persists across calls.
        self._gdd_total: float = 0.0
        # Separate lock for the GDD accumulator (base class lock protects
        # history/last_result; we guard our own state here).
        self._gdd_lock = _make_lock()

    # ------------------------------------------------------------------ #
    # AdaptationModule interface
    # ------------------------------------------------------------------ #
    def analyze(self, reading, context):
        """Analyze a temperature reading and accumulate GDD.

        Args:
            reading: A SensorReading whose ``metrics`` contain ``temp_c``
                (in °C), or ``None`` when no temperature data is available.
            context: Caller-supplied context dict (unused by this module
                but required by the AdaptationModule contract).

        Returns:
            An AdaptationResult whose ``data`` dict contains:

            * ``gdd_today``  — GDD contributed by this reading (0.0 if cold).
            * ``gdd_total``  — cumulative GDD after this reading.
            * ``stage``      — one of ``early``, ``mid``, ``peak``, ``late``.
        """
        # --- No reading at all ------------------------------------------ #
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No temperature data for GDD accumulation.",
                confidence=0.0,
                data={
                    "gdd_today": 0.0,
                    "gdd_total": self._gdd_total,
                    "stage": self._stage(),
                },
                severity="info",
            )

        temp_c = reading.metrics.get("temp_c")

        # Reading present but metric missing — treat as no data.
        if temp_c is None:
            logger.warning(
                "[%s] reading has no temp_c metric: %s", self.name, reading.metrics
            )
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No temperature data for GDD accumulation.",
                confidence=0.0,
                data={
                    "gdd_today": 0.0,
                    "gdd_total": self._gdd_total,
                    "stage": self._stage(),
                },
                severity="info",
            )

        # --- Too cold: no accumulation ---------------------------------- #
        if temp_c < self.BASE_TEMP:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    f"Too cold for GDD accumulation (base {self.BASE_TEMP:.0f}°C)."
                ),
                confidence=0.4,
                data={
                    "gdd_today": 0.0,
                    "gdd_total": self._gdd_total,
                    "stage": self._stage(),
                },
                severity="info",
            )

        # --- Warm day: accumulate GDD ----------------------------------- #
        # Approximation: use current temp as both max and min proxy.
        # See module-level docstring for the rationale and caveats.
        gdd_today = max(0.0, temp_c - self.BASE_TEMP)

        with self._gdd_lock:
            self._gdd_total += gdd_today
            total = self._gdd_total

        stage = self._stage_for_total(total)
        advisory, confidence = self._advisory_for_stage(stage, total)

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "gdd_today": round(gdd_today, 2),
                "gdd_total": round(total, 2),
                "stage": stage,
            },
            severity="info",
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _stage(self):
        """Return the current stage label without modifying state."""
        return self._stage_for_total(self._gdd_total)

    @staticmethod
    def _stage_for_total(total):
        """Map a cumulative GDD total to a season-stage label."""
        if total < EARLY_SEASON_LIMIT:
            return "early"
        if total < MID_SEASON_LIMIT:
            return "mid"
        if total < PEAK_SEASON_LIMIT:
            return "peak"
        return "late"

    @staticmethod
    def _advisory_for_stage(stage, total):
        """Return (advisory_text, confidence) for the given stage.

        NOTE: All stages use severity='info' because GDD tracking is an
        informational metric, not an alert. Confidence varies with how
        meaningful the accumulated total is for actionable guidance.
        """
        rounded = round(total, 1)
        if stage == "early":
            return (
                f"Early season — accumulated {rounded} GDD. "
                "Crops in early development stage.",
                0.5,
            )
        if stage == "mid":
            return (
                f"Mid season — accumulated {rounded} GDD. "
                "Active growth period.",
                0.6,
            )
        if stage == "peak":
            return (
                f"Peak season — accumulated {rounded} GDD. "
                "Many crops approaching maturity.",
                0.7,
            )
        # late
        return (
            f"Late season — accumulated {rounded} GDD. "
            "Harvest maturity approaching for most crops.",
            0.6,
        )

    # ------------------------------------------------------------------ #
    # Public accessors (useful for testing and dashboard integration)
    # ------------------------------------------------------------------ #
    @property
    def gdd_total(self):
        """Current cumulative GDD total."""
        with self._gdd_lock:
            return self._gdd_total

    def reset(self):
        """Reset the GDD accumulator to zero (e.g. start of a new season)."""
        with self._gdd_lock:
            self._gdd_total = 0.0