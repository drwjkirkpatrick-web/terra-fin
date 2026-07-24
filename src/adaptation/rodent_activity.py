"""Rodent activity adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It estimates rodent activity from night-mode motion events
and the current season, emitting advisories that range from 'no rodent
activity' (info) to 'high rodent activity detected' (warning).

WHY: Rodents cause significant damage in orchards by eating stored harvest,
gnawing bark, and nesting in equipment. Night-mode motion events are a strong
proxy for rodent presence because rodents are nocturnal. By combining motion
counts with seasonal awareness (rodent pressure spikes during harvest
months September–November), this module gives the farmer actionable guidance
— set traps, secure stored harvest, and monitor during peak pressure windows.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class RodentActivity(AdaptationModule):
    """Estimates rodent activity from night-mode motion events and season.

    Rodents are nocturnal, so night-mode motion events are a reliable proxy
    for their presence. The module classifies activity into four bands based
    on ``context['night_motion_count']`` (int, count of night-mode motion
    events):

        - > 10  → warning,   confidence 0.5, "high"
        - 5-10  → advisory,   confidence 0.4, "moderate"
        - 1-4   → info,      confidence 0.4, "low"
        - 0     → info,      confidence 0.5, "none"

    During harvest season (months 9–11, i.e. September–November) rodent
    pressure naturally increases. When ``context['month']`` is in [9, 10, 11]
    and motion_count > 3, the advisory appends a harvest-season note.

    When ``night_motion_count`` is absent from context entirely, the module
    reports insufficient data (confidence 0.0).

    The ``data`` dict always carries:
        - ``motion_count``   — the evaluated night motion count (int) or None
        - ``month``         — the evaluated month (int) or None
        - ``activity_level`` — one of "high", "moderate", "low", "none",
                               "no_data"
    """

    name = "rodent_activity"
    category = "animal"
    description = "Estimates rodent activity from night-mode motion events and season"

    #: Harvest-season months (September, October, November).
    _HARVEST_MONTHS = frozenset({9, 10, 11})

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading: SensorReading | None, context: dict) -> AdaptationResult:
        """Evaluate rodent activity for a single reading within context.

        Args:
            reading: Current SensorReading (may be None — this module is
                context-driven and does not require a sensor reading).
            context: Additional context.  Recognised keys:
                ``night_motion_count`` (int, count of night-mode motion events)
                and ``month`` (int 1-12, default 1).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        # No motion data at all — cannot estimate rodent activity.
        if "night_motion_count" not in context:
            return self._no_data_result()

        motion_count = context.get("night_motion_count", 0)
        month = context.get("month", 1)

        # Guard against non-integer motion count.
        if not isinstance(motion_count, int):
            logger.warning(
                "[%s] non-integer night_motion_count in context: %r",
                self.name,
                motion_count,
            )
            return self._no_data_result()

        # Classify rodent activity by motion count.
        if motion_count > 10:
            advisory = (
                "High rodent activity detected - frequent night motion. "
                "Set traps and secure stored harvest."
            )
            confidence = 0.5
            severity = "warning"
            activity_level = "high"
        elif motion_count >= 5:
            advisory = (
                "Moderate rodent activity - some night motion detected. "
                "Monitor and set traps."
            )
            confidence = 0.4
            severity = "advisory"
            activity_level = "moderate"
        elif motion_count >= 1:
            advisory = (
                "Low rodent activity - occasional night motion. "
                "Normal for orchard environment."
            )
            confidence = 0.4
            severity = "info"
            activity_level = "low"
        else:
            advisory = "No rodent activity detected."
            confidence = 0.5
            severity = "info"
            activity_level = "none"

        # Harvest-season note: rodent pressure naturally increases in Sep–Nov.
        if month in self._HARVEST_MONTHS and motion_count > 3:
            advisory += " Harvest season - rodent pressure naturally increases."

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "motion_count": motion_count,
                "month": month,
                "activity_level": activity_level,
            },
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _no_data_result(self) -> AdaptationResult:
        """Build the standard 'insufficient data' result."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="No motion data for rodent assessment.",
            confidence=0.0,
            data={
                "motion_count": None,
                "month": None,
                "activity_level": "no_data",
            },
            severity="info",
        )