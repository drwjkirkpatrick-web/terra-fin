"""Livestock proximity adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It detects nearby livestock (or other large animals) from
night-mode audio or motion patterns, emitting advisories that range from
'no significant motion' (info) to 'large animal detected nearby' (warning).

WHY: On farms and rural properties, knowing whether a large animal is nearby
at night helps with safety and predator/livestock management. The NightMode
sentinel classifies motion into bands (none, small_animal, human, large_animal)
based on acceleration-magnitude deltas; this module consumes that
classification as context and turns it into a proximity advisory the farmer
can act on — from low-concern small-animal detections to warnings that
something large may be close.

Context keys (all optional — sensible defaults apply):
    ``motion_pattern``    — str: "large_animal", "human", "small_animal", or
                            "none" (from NightModeSentinel.classify_motion).
    ``night_motion_count`` — int: cumulative motion events during the night.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class LivestockProximity(AdaptationModule):
    """Detects nearby livestock / animals from night-mode motion patterns.

    The module is context-driven: it reads ``context['motion_pattern']``
    (one of "large_animal", "human", "small_animal", "none") and
    ``context['night_motion_count']`` (int, default 0) to produce a proximity
    advisory.

    Advisory bands:
        - ``large_animal`` → warning,  confidence 0.5
        - ``human``        → advisory, confidence 0.5
        - ``small_animal`` → info,     confidence 0.4
        - ``none``/missing → info,     confidence 0.5

    The ``data`` dict always carries:
        - ``pattern``              — the evaluated motion pattern (str)
        - ``motion_count``         — the night motion count (int)
        - ``proximity_assessment`` — human-readable proximity summary (str)
    """

    name = "livestock_proximity"
    category = "animal"
    description = (
        "Detects nearby livestock from night-mode audio or motion patterns"
    )

    #: Valid motion patterns (aligned with NightModeSentinel.classify_motion).
    _PATTERNS = frozenset({"large_animal", "human", "small_animal", "none"})

    #: Mapping of pattern → (advisory, confidence, severity, proximity_assessment).
    _PATTERN_RESPONSES = {
        "large_animal": (
            "Large animal detected nearby - could be cattle, goats, or "
            "wildlife. Check your surroundings.",
            0.5,
            "warning",
            "Large animal in close proximity",
        ),
        "human": (
            "Human-sized motion detected - someone is nearby.",
            0.5,
            "advisory",
            "Human-sized presence nearby",
        ),
        "small_animal": (
            "Small animal detected - likely poultry or wildlife. Low concern.",
            0.4,
            "info",
            "Small animal nearby",
        ),
        "none": (
            "No significant motion detected nearby.",
            0.5,
            "info",
            "No nearby motion",
        ),
    }

    # ------------------------------------------------------------------ #
    # AdaptationModule interface
    # ------------------------------------------------------------------ #
    def analyze(self, reading, context):
        """Evaluate livestock proximity for a single reading within context.

        Args:
            reading: Current SensorReading (may be None — this module is
                context-driven and does not require a sensor reading).
            context: Additional context. Recognised keys:
                ``motion_pattern`` (str, default "none"),
                ``night_motion_count`` (int, default 0).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        pattern = context.get("motion_pattern", "none")
        motion_count = context.get("night_motion_count", 0)

        # Guard against an unexpected / unrecognised pattern.
        if pattern not in self._PATTERNS:
            logger.warning(
                "[%s] unrecognised motion_pattern %r — defaulting to none",
                self.name,
                pattern,
            )
            pattern = "none"

        advisory, confidence, severity, proximity = self._PATTERN_RESPONSES[
            pattern
        ]

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "pattern": pattern,
                "motion_count": motion_count,
                "proximity_assessment": proximity,
            },
            severity=severity,
        )