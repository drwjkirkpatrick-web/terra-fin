"""HarvestReadiness — integrates soil and maturity signals to assess harvest readiness.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It combines three independent factors — soil moisture, soil
pH, and days since flowering — into a single harvest-readiness assessment for a
given crop. Each factor is evaluated independently and the module reports the
narrowest actionable advisory: ready to harvest, mature but soil suboptimal,
or not yet mature.

WHY: Harvesting too early wastes the season's investment (fruit is undersized
and won't ripen properly); harvesting too late risks overripe fruit, pest
damage, and quality loss. Smallholder farmers rarely have lab-grade maturity
testing, but they do know when the crop flowered and can read a cheap soil
moisture / pH probe. By combining the three signals this module gives a
reliable go / no-go / wait signal tuned for the crops TerraFin tracks
(avocado, citrus). The per-crop maturity thresholds reflect agronomic
guidelines: avocado needs ~120 days from flowering, orange ~180 days.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Thresholds (see module docstring for rationale).                            #
# --------------------------------------------------------------------------- #
MOISTURE_LOW = 30.0        # below this, soil too dry for harvest conditions
MOISTURE_HIGH = 70.0       # above this, soil too wet / saturated
PH_LOW = 5.5               # below this, nutrient uptake compromised
PH_HIGH = 7.5              # above this, nutrient uptake compromised

# Per-crop maturity thresholds (days from flowering to harvest).
MATURITY_DAYS: dict[str, int] = {
    "avocado": 120,
    "orange": 180,
}
# Default maturity threshold for unrecognised crops (same as avocado).
DEFAULT_MATURITY_DAYS = 120


class HarvestReadiness(AdaptationModule):
    """Integrates soil moisture, pH, and maturity timing for harvest readiness.

    NOTE: This module is stateless — each ``analyze`` call evaluates the
    current reading and context independently. It reads ``soil_moisture_pct``
    and ``soil_pH`` from ``reading.metrics`` and ``days_since_flowering`` from
    ``context``. The crop type is taken from ``context['crop']`` (default
    ``'avocado'``).

    Factor checks (each evaluated independently):
        - moisture_ok: 30 < soil_moisture_pct < 70 (only when moisture is
          available in the reading).
        - pH_ok:       5.5 < soil_pH < 7.5 (only when pH is available).
        - days_ok:     days_since_flowering > maturity threshold for the crop
          (120 for avocado, 180 for orange, 120 default).

    Advisory priority (first match wins):
        1. No reading          → insufficient data.
        2. All three pass      → harvest readiness confirmed (info, conf 0.7).
        3. days_ok, moisture not ok → harvest soon, irrigate (advisory, 0.5).
        4. days_ok, pH not ok       → harvest, plan amendment (advisory, 0.5).
        5. not days_ok        → crop not yet mature (info, conf 0.6).
    """

    name: str = "harvest_readiness"
    category: str = "composite"
    description: str = (
        "Integrates soil moisture, pH, and maturity timing to assess "
        "overall harvest readiness for a crop"
    )

    # ------------------------------------------------------------------ #
    # Core analysis
    # ------------------------------------------------------------------ #

    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyse soil and maturity signals to assess harvest readiness.

        Args:
            reading: A SensorReading whose ``metrics`` dict may contain
                ``soil_moisture_pct`` (float, %) and ``soil_pH`` (float).
                ``None`` is handled gracefully.
            context: Caller-supplied context dict. ``context['crop']``
                (str, default ``'avocado'``) selects the maturity threshold.
                ``context['days_since_flowering']`` (int, default 0) is the
                days elapsed since the crop flowered.

        Returns:
            An AdaptationResult whose ``data`` dict always contains
            ``crop``, ``moisture_ok``, ``pH_ok``, ``days_ok``,
            ``maturity_days``, and ``readiness_score`` (0–3 count of
            factors passed).
        """
        crop: str = context.get("crop", "avocado")
        days_since_flowering: int = context.get("days_since_flowering", 0)
        maturity_days: int = MATURITY_DAYS.get(crop, DEFAULT_MATURITY_DAYS)

        # --- No reading → insufficient data ----------------------------- #
        if reading is None:
            return self._result(
                crop=crop,
                moisture_ok=False,
                pH_ok=False,
                days_ok=False,
                maturity_days=maturity_days,
                readiness_score=0,
                advisory="Insufficient data for harvest readiness assessment.",
                confidence=0.0,
                severity="info",
            )

        # --- Extract metrics from reading ------------------------------- #
        moisture = reading.metrics.get("soil_moisture_pct")
        ph = reading.metrics.get("soil_pH")

        moisture_ok: bool = (
            moisture is not None and MOISTURE_LOW < moisture < MOISTURE_HIGH
        )
        pH_ok: bool = (
            ph is not None and PH_LOW < ph < PH_HIGH
        )
        days_ok: bool = days_since_flowering > maturity_days

        readiness_score: int = sum([moisture_ok, pH_ok, days_ok])

        # --- All three factors pass → confirmed ------------------------- #
        if moisture_ok and pH_ok and days_ok:
            return self._result(
                crop=crop,
                moisture_ok=moisture_ok,
                pH_ok=pH_ok,
                days_ok=days_ok,
                maturity_days=maturity_days,
                readiness_score=readiness_score,
                advisory=(
                    f"Harvest readiness confirmed for {crop} - soil "
                    f"conditions and maturity timing aligned."
                ),
                confidence=0.7,
                severity="info",
            )

        # --- Mature but soil moisture not ideal ------------------------- #
        if days_ok and not moisture_ok:
            return self._result(
                crop=crop,
                moisture_ok=moisture_ok,
                pH_ok=pH_ok,
                days_ok=days_ok,
                maturity_days=maturity_days,
                readiness_score=readiness_score,
                advisory=(
                    "Crop mature but soil conditions not ideal - harvest "
                    "soon and irrigate remaining trees."
                ),
                confidence=0.5,
                severity="advisory",
            )

        # --- Mature but soil pH suboptimal ------------------------------ #
        if days_ok and not pH_ok:
            return self._result(
                crop=crop,
                moisture_ok=moisture_ok,
                pH_ok=pH_ok,
                days_ok=days_ok,
                maturity_days=maturity_days,
                readiness_score=readiness_score,
                advisory=(
                    "Crop mature but soil pH suboptimal - harvest and plan "
                    "soil amendment."
                ),
                confidence=0.5,
                severity="advisory",
            )

        # --- Not yet mature --------------------------------------------- #
        if not days_ok:
            return self._result(
                crop=crop,
                moisture_ok=moisture_ok,
                pH_ok=pH_ok,
                days_ok=days_ok,
                maturity_days=maturity_days,
                readiness_score=readiness_score,
                advisory=(
                    f"Crop not yet mature - {days_since_flowering} days "
                    f"since flowering. Need {maturity_days} days."
                ),
                confidence=0.6,
                severity="info",
            )

        # --- Fallback (should not normally be reached) ------------------ #
        logger.warning(
            "[%s] unhandled branch: crop=%s moisture_ok=%s pH_ok=%s days_ok=%s",
            self.name,
            crop,
            moisture_ok,
            pH_ok,
            days_ok,
        )
        return self._result(
            crop=crop,
            moisture_ok=moisture_ok,
            pH_ok=pH_ok,
            days_ok=days_ok,
            maturity_days=maturity_days,
            readiness_score=readiness_score,
            advisory="Insufficient data for harvest readiness assessment.",
            confidence=0.0,
            severity="info",
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _result(
        self,
        crop: str,
        moisture_ok: bool,
        pH_ok: bool,
        days_ok: bool,
        maturity_days: int,
        readiness_score: int,
        advisory: str,
        confidence: float,
        severity: str,
    ) -> AdaptationResult:
        """Build an AdaptationResult with the standard harvest-readiness data dict."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "crop": crop,
                "moisture_ok": moisture_ok,
                "pH_ok": pH_ok,
                "days_ok": days_ok,
                "maturity_days": maturity_days,
                "readiness_score": readiness_score,
            },
            severity=severity,
        )