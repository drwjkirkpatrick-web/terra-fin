"""NutrientDepletionEstimator — estimates nutrient depletion from harvest removal.

NOTE: This adaptation module tracks the cumulative nitrogen (N), phosphorus
(P), and potassium (K) removed from the soil by harvested produce. Every
kilogram of crop removed carries away a small but measurable quantity of
macronutrients; over multiple harvests these losses add up and must be
replaced to avoid soil mining and declining yields.

The per-crop N-P-K removal rates (grams per kilogram of harvested produce)
used here are rough agronomic estimates for the three crops TerraFin tracks:

    avocado : 3 g N, 0.5 g P, 4 g K per kg
    orange  : 2 g N, 0.4 g P, 3 g K per kg
    greens  : 4 g N, 0.8 g P, 5 g K per kg

These figures are NOT laboratory analysis values — they are published
rule-of-thumb ranges suitable for smallholder planning where soil testing
is unavailable. The module accumulates removal across calls so the farmer
gets a running picture of nutrient export since the last reset.

WHY: For smallholder farmers without access to soil labs, harvest-log-based
depletion estimation is the most practical way to decide when and what kind
of compost or fertilizer to apply. Nitrogen is the most commonly depleted
macronutrient under continuous harvest; potassium becomes limiting fastest
on sandy, high-rainfall soils. A timely advisory — "significant nitrogen
removed, consider compost" — lets the farmer replenish before deficiency
symptoms appear in the next crop cycle.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-crop macronutrient removal rates (grams of nutrient per kg of produce).
# Values are rough agronomic estimates, not lab measurements.
# ---------------------------------------------------------------------------
NPK_REMOVAL_RATES: dict[str, dict[str, float]] = {
    "avocado": {"n": 3.0, "p": 0.5, "k": 4.0},
    "orange": {"n": 2.0, "p": 0.4, "k": 3.0},
    "greens": {"n": 4.0, "p": 0.8, "k": 5.0},
}

# Cumulative thresholds (grams) above which an advisory is triggered.
NITROGEN_ADVISORY_THRESHOLD = 50.0  # grams of N removed since last reset
POTASSIUM_ADVISORY_THRESHOLD = 60.0  # grams of K removed since last reset


class NutrientDepletionEstimator(AdaptationModule):
    """Estimates nutrient depletion from harvest removal and soil conditions.

    NOTE: This module is stateful — it accumulates cumulative N, P, and K
    removal across ``analyze`` calls using the ``weight_kg`` field in
    ``context['harvest_data']``. The cumulative totals are stored internally
    and reported in every result's ``data`` dict so the dashboard and
    recorder can show running depletion. A new instance (or a manual reset of
    the internal counters) starts the accounting fresh.

    The module does not require a SensorReading; it works purely from the
    harvest context. When no harvest data is present it reports that it
    cannot estimate depletion.
    """

    name: str = "nutrient_depletion"
    category: str = "soil"
    description: str = (
        "Estimates nutrient depletion from harvest removal and soil conditions"
    )

    def __init__(self) -> None:
        super().__init__()
        # Cumulative nutrient removal since last reset (grams).
        self._total_n_g: float = 0.0
        self._total_p_g: float = 0.0
        self._total_k_g: float = 0.0
        self._crop_type: str | None = None

    # ------------------------------------------------------------------ #
    # Core analysis
    # ------------------------------------------------------------------ #

    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyze harvest data and estimate cumulative nutrient depletion.

        Args:
            reading: A SensorReading (unused by this module but required by
                the AdaptationModule contract), or None.
            context: Caller-supplied context dict. ``context['harvest_data']``
                is expected to contain ``crop_type`` (or ``crop``) and
                ``weight_kg`` keys. If the dict is empty or absent the module
                reports that it cannot estimate depletion.

        Returns:
            An AdaptationResult whose ``data`` dict always contains
            ``total_n_g``, ``total_p_g``, ``total_k_g``, and ``crop_type``.
            When thresholds are crossed the advisory and severity escalate.
        """
        harvest_data: dict = context.get("harvest_data", {})

        # --- No harvest data → cannot estimate ---------------------------- #
        if not harvest_data or not harvest_data.get("weight_kg"):
            return self._result(
                advisory=(
                    "No harvest data - cannot estimate nutrient depletion."
                ),
                confidence=0.2,
                severity="info",
            )

        weight_kg: float = float(harvest_data.get("weight_kg", 0.0))
        if weight_kg <= 0:
            return self._result(
                advisory=(
                    "No harvest data - cannot estimate nutrient depletion."
                ),
                confidence=0.2,
                severity="info",
            )

        # Determine the crop type (accept both 'crop_type' and 'crop' keys).
        crop_type: str = (
            harvest_data.get("crop_type")
            or harvest_data.get("crop")
            or "unknown"
        ).lower()
        self._crop_type = crop_type

        # Look up the removal rates for this crop.
        rates = NPK_REMOVAL_RATES.get(crop_type)
        if rates is None:
            logger.warning(
                "[%s] unknown crop type %r — no NPK rates available",
                self.name,
                crop_type,
            )
            return self._result(
                advisory=(
                    f"Unknown crop type '{crop_type}' — cannot estimate "
                    f"nutrient removal."
                ),
                confidence=0.2,
                severity="info",
            )

        # Accumulate removal for this harvest event.
        n_removed = rates["n"] * weight_kg
        p_removed = rates["p"] * weight_kg
        k_removed = rates["k"] * weight_kg

        self._total_n_g += n_removed
        self._total_p_g += p_removed
        self._total_k_g += k_removed

        logger.debug(
            "[%s] harvest %.1f kg %s: +%.1f g N, +%.1f g P, +%.1f g K "
            "(cumulative N=%.1f P=%.1f K=%.1f)",
            self.name,
            weight_kg,
            crop_type,
            n_removed,
            p_removed,
            k_removed,
            self._total_n_g,
            self._total_p_g,
            self._total_k_g,
        )

        # Evaluate thresholds — nitrogen advisory takes priority.
        if self._total_n_g > NITROGEN_ADVISORY_THRESHOLD:
            return self._result(
                advisory=(
                    "Significant nitrogen removed by harvest - consider "
                    "compost or N fertilizer."
                ),
                confidence=0.5,
                severity="advisory",
            )

        if self._total_k_g > POTASSIUM_ADVISORY_THRESHOLD:
            return self._result(
                advisory="High potassium removal - apply potash.",
                confidence=0.5,
                severity="advisory",
            )

        # Below thresholds — routine informational update.
        return self._result(
            advisory=(
                f"Harvest recorded: {weight_kg:.1f} kg {crop_type}. "
                f"Cumulative removal N={self._total_n_g:.1f} g, "
                f"P={self._total_p_g:.1f} g, K={self._total_k_g:.1f} g."
            ),
            confidence=0.3,
            severity="info",
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _result(
        self,
        advisory: str,
        confidence: float,
        severity: str,
    ) -> AdaptationResult:
        """Build an AdaptationResult with the standard nutrient data dict."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "total_n_g": round(self._total_n_g, 2),
                "total_p_g": round(self._total_p_g, 2),
                "total_k_g": round(self._total_k_g, 2),
                "crop_type": self._crop_type,
            },
            severity=severity,
        )

    def reset(self) -> None:
        """Reset cumulative nutrient removal counters to zero."""
        self._total_n_g = 0.0
        self._total_p_g = 0.0
        self._total_k_g = 0.0
        self._crop_type = None