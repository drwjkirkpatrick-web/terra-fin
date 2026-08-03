"""Bird scavenger adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It estimates bird pressure on ripe fruit based on the time
of day and whether crops are currently ripening, emitting advisories that
range from 'good time to harvest' (info) to 'protect ripe fruit' (warning).

WHY: Birds cause significant losses in orchards and berry patches by feeding
on ripe fruit, particularly at dawn and dusk when foraging peaks. By
combining time-of-day awareness with the crop-ripening flag, this module
gives the farmer actionable guidance — deploy netting or scaring devices
before peak foraging windows, or harvest ripe fruit before evening when
birds return to feed.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class BirdScavengerMonitor(AdaptationModule):
    """Estimates bird pressure on ripe fruit from time of day and harvest season.

    Birds are most active at dawn (hours 6-9) and dusk (hours 16-18). Midday
    hours (10-15) are lower risk, while night hours (19-5) carry minimal risk
    because birds are roosting.

    Context is supplied via ``context['hour']`` (int 0-23, default 12) and
    ``context['crop_ripening']`` (bool, default False).

    Advisory bands (only meaningful when ``crop_ripening`` is True):
        - dawn   (hour in 6-9)    → warning, confidence 0.6
        - dusk   (hour in 16-18)  → warning, confidence 0.6
        - midday (hour in 10-15)  → info,    confidence 0.5
        - night  (hour in 19-5)   → info,    confidence 0.6

    When ``crop_ripening`` is False the module reports minimal bird pressure
    regardless of hour. When no context is supplied the module reports
    insufficient data.

    The ``data`` dict always carries:
        - ``hour``            — the evaluated hour (int) or None
        - ``crop_ripening``   — whether crops were flagged as ripening
        - ``bird_activity``  — one of "high_dawn", "high_dusk", "low_midday",
                                "roosting"
    """

    name = "bird_scavenger"
    category = "animal"
    description = "Estimates bird pressure on ripe fruit from time of day and season"

    #: Hour windows.
    _DAWN_HOURS = frozenset({6, 7, 8, 9})
    _DUSK_HOURS = frozenset({16, 17, 18})
    _MIDDAY_HOURS = frozenset({10, 11, 12, 13, 14, 15})
    _NIGHT_HOURS = frozenset({19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5})

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading, context):
        """Evaluate bird pressure for a single reading within context.

        Args:
            reading: Current SensorReading (may be None — this module is
                context-driven and does not require a sensor reading).
            context: Additional context.  Recognised keys:
                ``hour`` (int 0-23, default 12), ``crop_ripening`` (bool).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        # Default hour to 12 (midday) when not provided.
        hour = context.get("hour", 12)
        crop_ripening = context.get("crop_ripening", False)

        # No context at all — cannot estimate bird pressure.
        if "hour" not in context and "crop_ripening" not in context:
            return self._no_data_result()

        # Resolve hour to an int for membership tests.
        if not isinstance(hour, int):
            logger.warning("[%s] non-integer hour in context: %r", self.name, hour)
            return self._no_data_result()

        # If crops are not ripening, bird pressure is minimal regardless of hour.
        if not crop_ripening:
            advisory = "No ripe crops - bird pressure minimal."
            confidence = 0.5
            severity = "info"
            bird_activity = self._activity_for_hour(hour)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=advisory,
                confidence=confidence,
                data={
                    "hour": hour,
                    "crop_ripening": False,
                    "bird_activity": bird_activity,
                },
                severity=severity,
            )

        # Crops are ripening — classify by time-of-day window.
        if hour in self._DAWN_HOURS:
            advisory = (
                "Birds active at dawn - protect ripe fruit with netting or "
                "scaring devices."
            )
            confidence = 0.6
            severity = "warning"
            bird_activity = "high_dawn"
        elif hour in self._DUSK_HOURS:
            advisory = "Birds active at dusk - harvest ripe fruit before evening."
            confidence = 0.6
            severity = "warning"
            bird_activity = "high_dusk"
        elif hour in self._MIDDAY_HOURS:
            advisory = "Birds less active midday - good time for harvesting."
            confidence = 0.5
            severity = "info"
            bird_activity = "low_midday"
        else:  # hour in night hours
            advisory = "Birds roosting - low risk during night."
            confidence = 0.6
            severity = "info"
            bird_activity = "roosting"

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "hour": hour,
                "crop_ripening": True,
                "bird_activity": bird_activity,
            },
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _activity_for_hour(self, hour):
        """Map an hour to a bird_activity label (used for the no-ripening path)."""
        if hour in self._DAWN_HOURS:
            return "high_dawn"
        if hour in self._DUSK_HOURS:
            return "high_dusk"
        if hour in self._MIDDAY_HOURS:
            return "low_midday"
        return "roosting"

    def _no_data_result(self):
        """Build the standard 'insufficient data' result."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="Insufficient data for bird pressure estimate.",
            confidence=0.0,
            data={
                "hour": None,
                "crop_ripening": None,
                "bird_activity": None,
            },
            severity="info",
        )