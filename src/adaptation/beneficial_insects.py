"""Beneficial insect habitat index adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It estimates the quality of habitat for beneficial insects
(ladybugs, lacewings, hoverflies, parasitic wasps) based on flowering plant
diversity and recent pesticide use.

WHY: Beneficial insects are the foundation of natural pest control. A diverse
flowering understory provides nectar and pollen that sustain predatory
insects throughout the season. Pesticide applications — even organic ones —
can decimate beneficial populations for weeks. By combining flowering
availability with pesticide history, this module gives the farmer an
actionable signal: plant more companion flowers, avoid spraying, or allow
recovery time.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class BeneficialInsectIndex(AdaptationModule):
    """Estimates beneficial insect habitat quality.

    Reads ``flowering_plants`` (int) and ``pesticide_used_recently`` (bool)
    from the context dict, and optionally extracts ``temp_c`` from a
    SensorReading when available.

    Decision logic (checked in priority order):

        - ``pesticide_used_recently`` is True → warning (overrides all).
        - ``flowering_plants`` > 5 → excellent habitat (info).
        - ``flowering_plants`` 2-5 → moderate habitat (info).
        - ``flowering_plants`` < 2 → low habitat (advisory).
        - ``flowering_plants`` absent from context → insufficient data.

    When a temperature reading above 35 °C is available, an additional
    sentence about extreme heat is appended to the advisory.

    The ``data`` dict always carries:
        - ``flowering_count``  — number of flowering plants or None
        - ``pesticide_recent`` — bool, pesticide recently applied
        - ``temp``             — temperature (°C) or None
        - ``habitat_quality``  — one of "excellent", "moderate", "low",
                                 "reduced", or "no_data"
    """

    name: str = "beneficial_insects"
    category: str = "insect"
    description: str = (
        "Estimates beneficial insect habitat quality from flowering "
        "availability and pesticide-free conditions"
    )

    #: Flowering plant count thresholds.
    _EXCELLENT_THRESHOLD = 5   # > 5 → excellent habitat
    _MODERATE_THRESHOLD = 2    # 2-5 → moderate habitat
    #: Temperature above which beneficial insect activity drops.
    _EXTREME_HEAT_THRESHOLD = 35.0

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(
        self, reading: SensorReading | None, context: dict
    ) -> AdaptationResult:
        """Evaluate beneficial insect habitat quality.

        Args:
            reading: Current SensorReading (may be None). When present,
                ``temp_c`` is extracted from ``metrics`` for the extreme-heat
                check.
            context: Context dict. Recognised keys:
                ``flowering_plants`` (int), ``pesticide_used_recently`` (bool).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        # No flowering_plants key at all — cannot assess habitat.
        if "flowering_plants" not in context:
            return self._no_data_result(reading)

        flowering = context.get("flowering_plants", 0)
        pesticide_recent = bool(context.get("pesticide_used_recently", False))

        # Extract temperature from reading if available.
        temp_c = None
        if reading is not None:
            temp_c = reading.metrics.get("temp_c")

        # ------------------------------------------------------------------
        # Classify habitat quality. Pesticide use takes priority because it
        # overrides any flowering benefit — beneficials are killed outright.
        # ------------------------------------------------------------------
        if pesticide_recent:
            advisory = (
                "Pesticide recently applied - beneficial insects may be "
                "reduced. Allow recovery time."
            )
            confidence = 0.6
            severity = "warning"
            habitat_quality = "reduced"
        elif flowering > self._EXCELLENT_THRESHOLD:
            advisory = (
                "Excellent beneficial insect habitat - diverse flowers and "
                "no pesticides. Ladybugs and lacewings likely present."
            )
            confidence = 0.7
            severity = "info"
            habitat_quality = "excellent"
        elif flowering >= self._MODERATE_THRESHOLD:
            advisory = (
                "Moderate beneficial insect habitat - consider planting more "
                "flowering companion plants."
            )
            confidence = 0.5
            severity = "info"
            habitat_quality = "moderate"
        else:
            # flowering < 2
            advisory = (
                "Low flowering plant diversity - plant marigolds or "
                "sunflowers to attract beneficials."
            )
            confidence = 0.5
            severity = "advisory"
            habitat_quality = "low"

        # Append extreme-heat caveat when a high temperature reading exists.
        if temp_c is not None and temp_c > self._EXTREME_HEAT_THRESHOLD:
            advisory += " Extreme heat reduces beneficial insect activity."

        data = {
            "flowering_count": flowering,
            "pesticide_recent": pesticide_recent,
            "temp": temp_c,
            "habitat_quality": habitat_quality,
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
    def _no_data_result(self, reading: SensorReading | None) -> AdaptationResult:
        """Build the standard 'insufficient data' result.

        Still extracts temp if a reading is available so the data dict is
        complete, but the advisory and confidence reflect that habitat
        assessment is not possible.
        """
        temp_c = None
        if reading is not None:
            temp_c = reading.metrics.get("temp_c")

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="Insufficient data for beneficial insect assessment.",
            confidence=0.0,
            data={
                "flowering_count": None,
                "pesticide_recent": False,
                "temp": temp_c,
                "habitat_quality": "no_data",
            },
            severity="info",
        )