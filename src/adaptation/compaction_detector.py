"""Soil compaction detection adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It estimates soil compaction by combining soil moisture
data with an IMU-derived probe-resistance signal, giving the farmer a
quick field-level indicator of whether aeration is needed.

WHY: Soil compaction restricts root growth and water infiltration, but it is
hard to diagnose in isolation — wet soil that resists probe insertion is very
likely compacted, while wet soil that accepts a probe easily is not. Dry hard
soil can mimic compaction, so the module asks the farmer to wait for moisture
before drawing a firm conclusion. Combining the two signals avoids false
positives that a single-sensor threshold would produce.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class CompactionDetector(AdaptationModule):
    """Estimates soil compaction from moisture and probe-insertion resistance.

    Uses ``soil_moisture_pct`` from the sensor reading and
    ``probe_resistance`` (0.0–1.0) from the context dict.  The probe-resistance
    value simulates the resistance felt when inserting a soil probe, which in
    a real deployment would be derived from IMU force/acceleration data.

    Decision rules:
        - moisture > 60%  and resistance > 0.7  → compaction likely (advisory)
        - moisture > 60%  and resistance < 0.3  → no compaction (info)
        - moisture < 30% and resistance > 0.5  → dry hard soil, defer (info)
        - otherwise                         → moderate / inconclusive (info)
    """

    name = "compaction_detector"
    category = "soil"
    description = "Estimates soil compaction from moisture and probe resistance"

    # Thresholds — exposed as class attributes for readability / tuning.
    _WET_MOISTURE_THRESHOLD = 60.0   # % — above this the soil is "wet"
    _DRY_MOISTURE_THRESHOLD = 30.0  # % — below this the soil is "dry"
    _HIGH_RESISTANCE_THRESHOLD = 0.7
    _LOW_RESISTANCE_THRESHOLD = 0.3
    _DRY_HIGH_RESISTANCE_THRESHOLD = 0.5

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading: SensorReading | None, context: dict) -> AdaptationResult:
        """Analyze a soil reading + context and return a compaction advisory.

        Args:
            reading:  Current SensorReading (may be None).
            context:  dict that may contain ``probe_resistance`` (0.0–1.0),
                      simulating IMU-derived resistance to probe insertion.

        Returns:
            AdaptationResult with advisory, confidence, severity, and a data
            dict containing ``moisture``, ``resistance_estimate`` and
            ``compaction_risk``.
        """
        # --- No reading at all ---
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil data for compaction assessment.",
                confidence=0.0,
                data={
                    "moisture": None,
                    "resistance_estimate": context.get("probe_resistance", 0.0),
                    "compaction_risk": "unknown",
                },
                severity="info",
            )

        moisture = reading.metrics.get("soil_moisture_pct")
        if moisture is None:
            # No soil-moisture metric — treat as no data.
            logger.warning(
                "[%s] reading has no soil_moisture_pct metric: %s",
                self.name,
                reading.metrics,
            )
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil data for compaction assessment.",
                confidence=0.0,
                data={
                    "moisture": None,
                    "resistance_estimate": context.get("probe_resistance", 0.0),
                    "compaction_risk": "unknown",
                },
                severity="info",
            )

        # Probe resistance comes from the context dict (simulated IMU signal).
        resistance_estimate = float(context.get("probe_resistance", 0.0))

        # --- Decision tree ------------------------------------------------
        if moisture > self._WET_MOISTURE_THRESHOLD:
            if resistance_estimate > self._HIGH_RESISTANCE_THRESHOLD:
                advisory = (
                    "Soil compaction likely - wet soil with high probe "
                    "resistance. Consider aerating."
                )
                confidence = 0.5
                severity = "advisory"
                compaction_risk = "high"
            elif resistance_estimate < self._LOW_RESISTANCE_THRESHOLD:
                advisory = (
                    "Wet soil but low resistance - no compaction detected."
                )
                confidence = 0.4
                severity = "info"
                compaction_risk = "low"
            else:
                advisory = (
                    "Wet soil with moderate probe resistance - compaction "
                    "uncertain. Monitor conditions."
                )
                confidence = 0.3
                severity = "info"
                compaction_risk = "moderate"
        elif moisture < self._DRY_MOISTURE_THRESHOLD:
            if resistance_estimate > self._DRY_HIGH_RESISTANCE_THRESHOLD:
                advisory = (
                    "Dry hard soil - may be compacted. Wait for moisture "
                    "before assessing."
                )
                confidence = 0.3
                severity = "info"
                compaction_risk = "moderate"
            else:
                advisory = (
                    "Dry soil with low resistance - no compaction detected."
                )
                confidence = 0.4
                severity = "info"
                compaction_risk = "low"
        else:
            advisory = (
                "Soil moisture is moderate - compaction assessment "
                "inconclusive at this moisture level."
            )
            confidence = 0.25
            severity = "info"
            compaction_risk = "unknown"

        data = {
            "moisture": moisture,
            "resistance_estimate": resistance_estimate,
            "compaction_risk": compaction_risk,
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