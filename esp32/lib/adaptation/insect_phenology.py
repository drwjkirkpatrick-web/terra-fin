"""Insect phenology adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It tracks insect development stages using growing degree
days (GDD) specific to pests.  Unlike the crop-focused ``GrowingDegreeDays``
module, this module uses a base temperature of 10 °C as a generalised default
for common agricultural insect pests and maps accumulated pest GDD to
phenological stages (early development, larval, pupal/adult, peak adult
activity, late generation).

WHY: Insect pests follow predictable degree-day-driven life cycles.  Knowing
the accumulated heat units lets a farmer anticipate when larvae will begin
feeding, when adults will emerge and mate, and when a second generation may
appear — enabling timely monitoring and intervention rather than reactive
damage control.  This is particularly valuable for smallholder plots where
preventative scouting reduces pesticide use and crop loss.

APPROXIMATION: The GDD formula mirrors the one used by ``GrowingDegreeDays``:
each reading's temperature is treated as a proxy for both daily max and min,
giving ``pest_gdd ≈ max(0, T_current - T_base)``.  This overestimates GDD on
hot midday readings and underestimates it on cool-morning readings.  The
approximation is documented so downstream consumers know the uncertainty.
When true daily max/min data becomes available the formula should be
upgraded accordingly.

The base temperature (10 °C) is a generalised default for common pests such
as corn earworm, European corn borer, and codling moth.  Pest-specific
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
# Pest development thresholds (cumulative GDD).
# These are generalised bands for common agricultural insect pests.
# Individual pest species have their own degree-day requirements, but these
# ranges give useful coarse guidance for a mixed smallholder plot.
# --------------------------------------------------------------------------- #
EARLY_DEVELOPMENT_LIMIT = 50      # < 50  → early development (eggs, early larvae)
LARVAL_LIMIT = 150               # 50–150 → larval stage
PUPAL_LIMIT = 300                 # 150–300 → pupating / emerging adults
ADULT_LIMIT = 500                 # 300–500 → peak adult activity
# > 500 → late generation, possible second cycle


class InsectPhenology(AdaptationModule):
    """Tracks insect development stages using growing degree days.

    Each call to :meth:`analyze` with a valid temperature reading adds that
    reading's contribution to the internal ``_pest_gdd`` accumulator and
    returns an advisory describing the current pest development stage.

    Thread-safety: accumulation is guarded by a re-entrant lock so the
    module can be polled concurrently by the orchestrator.
    """

    name: str = "insect_phenology"
    category: str = "insect"
    description: str = (
        "Tracks insect development stages using growing degree days specific to pests"
    )

    #: Base temperature (°C) below which insect development is assumed to stall.
    BASE_TEMP: float = 10.0

    def __init__(self):
        super().__init__()
        # Cumulative pest GDD accumulator — persists across calls.
        self._pest_gdd: float = 0.0
        # Separate lock for the GDD accumulator (base class lock protects
        # history/last_result; we guard our own state here).
        self._gdd_lock = _make_lock()

    # ------------------------------------------------------------------ #
    # AdaptationModule interface
    # ------------------------------------------------------------------ #
    def analyze(self, reading, context):
        """Analyze a temperature reading and accumulate pest GDD.

        Args:
            reading: A SensorReading whose ``metrics`` contain ``temp_c``
                (in °C), or ``None`` when no temperature data is available.
            context: Caller-supplied context dict (unused by this module
                but required by the AdaptationModule contract).

        Returns:
            An AdaptationResult whose ``data`` dict contains:

            * ``pest_gdd``    — cumulative pest GDD after this reading.
            * ``stage``       — one of ``early``, ``larval``, ``pupal``,
                               ``adult``, ``late``.
            * ``risk_level``  — qualitative risk descriptor for the stage.
        """
        # --- No reading at all ------------------------------------------ #
        if reading is None:
            return self._no_data_result()

        temp_c = reading.metrics.get("temp_c")

        # Reading present but metric missing — treat as no data.
        if temp_c is None:
            logger.warning(
                "[%s] reading has no temp_c metric: %s", self.name, reading.metrics
            )
            return self._no_data_result()

        # --- Too cold: no accumulation ---------------------------------- #
        if temp_c < self.BASE_TEMP:
            # No development below the base temperature, but preserve the
            # existing accumulated total.
            stage = self._stage_for_total(self._pest_gdd)
            risk_level = self._risk_for_stage(stage)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=(
                    f"Temperature below development base ({self.BASE_TEMP:.0f}°C). "
                    "No insect development expected."
                ),
                confidence=0.3,
                data={
                    "pest_gdd": round(self._pest_gdd, 2),
                    "stage": stage,
                    "risk_level": risk_level,
                },
                severity="info",
            )

        # --- Warm reading: accumulate pest GDD --------------------------- #
        gdd_today = max(0.0, temp_c - self.BASE_TEMP)

        with self._gdd_lock:
            self._pest_gdd += gdd_today
            total = self._pest_gdd

        stage = self._stage_for_total(total)
        advisory, confidence, severity = self._advisory_for_stage(stage)

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "pest_gdd": round(total, 2),
                "stage": stage,
                "risk_level": self._risk_for_stage(stage),
            },
            severity=severity,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _stage_for_total(total):
        """Map a cumulative pest GDD total to a development-stage label."""
        if total < EARLY_DEVELOPMENT_LIMIT:
            return "early"
        if total < LARVAL_LIMIT:
            return "larval"
        if total < PUPAL_LIMIT:
            return "pupal"
        if total < ADULT_LIMIT:
            return "adult"
        return "late"

    @staticmethod
    def _risk_for_stage(stage):
        """Return a qualitative risk descriptor for the given stage."""
        risks = {
            "early": "low",
            "larval": "moderate",
            "pupal": "moderate",
            "adult": "high",
            "late": "low",
        }
        return risks.get(stage, "unknown")

    @staticmethod
    def _advisory_for_stage(stage):
        """Return (advisory_text, confidence, severity) for the given stage."""
        if stage == "early":
            return (
                "Insects in early development - eggs and early larvae. "
                "Low crop damage expected.",
                0.4,
                "info",
            )
        if stage == "larval":
            return (
                "Insects in larval stage - monitoring critical. "
                "Check for feeding damage.",
                0.5,
                "advisory",
            )
        if stage == "pupal":
            return (
                "Insects pupating or emerging as adults - peak activity approaching.",
                0.5,
                "advisory",
            )
        if stage == "adult":
            return (
                "Adult insect peak activity - mating and egg-laying. "
                "Maximum crop risk.",
                0.6,
                "warning",
            )
        # late
        return (
            "Late generation insects - second cycle may begin. "
            "Monitor for resurgence.",
            0.4,
            "info",
        )

    def _no_data_result(self):
        """Build the standard 'no temperature data' result."""
        stage = self._stage_for_total(self._pest_gdd)
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="No temperature data for insect phenology.",
            confidence=0.0,
            data={
                "pest_gdd": round(self._pest_gdd, 2),
                "stage": stage,
                "risk_level": self._risk_for_stage(stage),
            },
            severity="info",
        )

    # ------------------------------------------------------------------ #
    # Public accessors (useful for testing and dashboard integration)
    # ------------------------------------------------------------------ #
    @property
    def pest_gdd(self):
        """Current cumulative pest GDD total."""
        with self._gdd_lock:
            return self._pest_gdd

    def reset(self):
        """Reset the pest GDD accumulator to zero (e.g. start of a new season)."""
        with self._gdd_lock:
            self._pest_gdd = 0.0