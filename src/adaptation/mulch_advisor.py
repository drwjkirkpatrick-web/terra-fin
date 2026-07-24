"""Mulch advisor adaptation module for the Terra-Fin agent.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It recommends mulching based on soil moisture, soil
temperature, and erosion risk so the grower can protect bare soil before
moisture is lost or topsoil washes away.

WHY: Mulch is one of the cheapest soil-conservation interventions available —
it suppresses evaporation, moderates soil temperature, and shields bare
earth from wind and water erosion. The decision to mulch, however, depends on
several interacting factors: very dry soil needs immediate cover, hot soil
benefits from the cooling effect, and bare soil at erosion risk should be
mulched regardless of moisture. Conversely, already-saturated soil should
not be mulched because trapped moisture promotes fungal problems. This
module weighs those conditions in a defined priority order and emits a
confidence/severity-tagged advisory the orchestrator can act on.
"""

from __future__ import annotations

import logging
from typing import Any

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class MulchAdvisor(AdaptationModule):
    """Recommends mulching based on soil moisture, temperature, and erosion risk.

    The ``analyze`` method extracts ``soil_moisture_pct`` from the reading
    metrics and pulls ``soil_temp_c`` (default 25.0 °C) and ``erosion_risk``
    (default ``"low"``) from the context dict. Conditions are checked in
    priority order — the most urgent situation wins:

        1. ``erosion_risk == "high"`` — warning; mulch urgently needed to
           protect bare soil, regardless of moisture.
        2. ``moisture < 30 %`` — advisory; apply mulch now to conserve the
           remaining soil moisture.
        3. ``30 % ≤ moisture ≤ 50 %`` **and** ``soil_temp > 30 °C`` —
           advisory; mulch to reduce evaporation and cool the soil.
        4. ``50 % < moisture ≤ 70 %`` — info; mulch beneficial but not urgent.
        5. ``moisture > 70 %`` — info; delay mulching to avoid fungal issues.
    """

    name: str = "mulch_advisor"
    category: str = "soil"
    description: str = (
        "Recommends mulching based on soil moisture, temperature, and erosion risk"
    )

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Analyse a soil reading and context, returning a mulch advisory.

        Args:
            reading: A SensorReading whose metrics contain
                ``soil_moisture_pct``, or None when no data is available.
            context: Caller-supplied context dict. Recognised keys:
                ``soil_temp_c`` (float, default 25.0) and
                ``erosion_risk`` (str, default ``"low"``).

        Returns:
            An AdaptationResult with the advisory, confidence, severity, and
            a data dict containing ``moisture``, ``soil_temp``,
            ``erosion_risk``, and ``mulch_priority``.
        """
        soil_temp = float(context.get("soil_temp_c", 25.0))
        erosion_risk = context.get("erosion_risk", "low")

        # No reading at all — report the absence honestly.
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil data for mulch recommendation.",
                confidence=0.0,
                data={
                    "moisture": None,
                    "soil_temp": soil_temp,
                    "erosion_risk": erosion_risk,
                    "mulch_priority": "unknown",
                },
                severity="info",
            )

        moisture = reading.metrics.get("soil_moisture_pct")

        # Reading present but the metric is missing — treat as no data.
        if moisture is None:
            logger.warning(
                "[%s] reading has no soil_moisture_pct metric: %s",
                self.name,
                reading.metrics,
            )
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil data for mulch recommendation.",
                confidence=0.0,
                data={
                    "moisture": None,
                    "soil_temp": soil_temp,
                    "erosion_risk": erosion_risk,
                    "mulch_priority": "unknown",
                },
                severity="info",
            )

        moisture = float(moisture)

        # --------------------------------------------------------------
        # Priority order — check the most urgent condition first so the
        # worst situation always wins.
        # --------------------------------------------------------------
        if erosion_risk == "high":
            advisory = (
                "Mulch urgently needed - bare soil at erosion risk. "
                "Apply straw or leaves."
            )
            confidence = 0.7
            severity = "warning"
            priority = "high"
        elif moisture < 30.0:
            advisory = (
                "Apply mulch now - conserve remaining soil moisture. "
                "Use 5-10cm organic mulch."
            )
            confidence = 0.7
            severity = "advisory"
            priority = "high"
        elif moisture <= 50.0 and soil_temp > 30.0:
            advisory = "Mulch recommended - reduce evaporation and cool soil."
            confidence = 0.6
            severity = "advisory"
            priority = "medium"
        elif moisture <= 70.0:
            advisory = "Mulch beneficial but not urgent."
            confidence = 0.4
            severity = "info"
            priority = "low"
        else:
            advisory = "Soil wet - delay mulching to avoid fungal issues."
            confidence = 0.5
            severity = "info"
            priority = "low"

        data = {
            "moisture": moisture,
            "soil_temp": soil_temp,
            "erosion_risk": erosion_risk,
            "mulch_priority": priority,
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