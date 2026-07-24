"""Grazing pressure adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It estimates livestock grazing pressure from GPS track
overlap (how much time animals spend in a given area) combined with ground
cover percentage, emitting advisories that range from 'minimal grazing
pressure' (info) to 'heavy grazing detected - consider rest period' (warning).

WHY: Overgrazing degrades pasture health by stripping ground cover, exposing
soil to erosion, and compacting roots. By combining GPS track density — a
proxy for how long livestock linger in a paddock — with ground cover
observations, this module gives the grazier actionable guidance: rotate
animals out of heavily used areas before cover collapses, and confirm when
light pressure allows continued grazing.
"""

from __future__ import annotations

import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class GrazingPressure(AdaptationModule):
    """Estimates livestock grazing pressure from GPS track overlap and ground cover.

    Track density (``context['gps_track_density']``, 0.0-1.0, higher means more
    time spent in the area) captures how intensely livestock have used a
    paddock. Ground cover (``context['ground_cover_pct']``, 0-100, default 50)
    reflects the residual vegetation protecting the soil.

    Advisory bands:
        - track_density > 0.7 and ground_cover < 30
            → warning,  confidence 0.6  ("Heavy grazing detected …")
        - track_density > 0.7 and 30 ≤ ground_cover ≤ 60
            → advisory, confidence 0.5  ("Moderate grazing …")
        - 0.3 ≤ track_density ≤ 0.7
            → info,     confidence 0.4  ("Light to moderate grazing …")
        - track_density < 0.3
            → info,     confidence 0.5  ("Minimal grazing pressure …")
        - no context keys supplied
            → info,     confidence 0.0  ("No grazing data available.")

    The ``data`` dict always carries:
        - ``track_density``   — the evaluated GPS density (float) or None
        - ``ground_cover``    — the evaluated ground cover pct (float) or None
        - ``pressure_level``  — one of "heavy", "moderate", "light",
                                "minimal", or "unknown"
    """

    name = "grazing_pressure"
    category = "animal"
    description = "Estimates livestock grazing pressure from GPS track overlap and ground cover"

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading: SensorReading | None, context: dict) -> AdaptationResult:
        """Evaluate grazing pressure for a single reading within context.

        Args:
            reading: Current SensorReading (may be None — this module is
                context-driven and does not require a sensor reading).
            context: Additional context.  Recognised keys:
                ``gps_track_density`` (float 0.0-1.0, default 0.0),
                ``ground_cover_pct`` (float 0-100, default 50).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data.
        """
        # No grazing context at all — cannot estimate pressure.
        if "gps_track_density" not in context and "ground_cover_pct" not in context:
            return self._no_data_result()

        track_density = context.get("gps_track_density", 0.0)
        ground_cover = context.get("ground_cover_pct", 50)

        # Guard against non-numeric input.
        if not isinstance(track_density, (int, float)) or not isinstance(
            ground_cover, (int, float)
        ):
            logger.warning(
                "[%s] non-numeric context: track_density=%r ground_cover=%r",
                self.name,
                track_density,
                ground_cover,
            )
            return self._no_data_result()

        # Heavy use of the area.
        if track_density > 0.7:
            if ground_cover < 30:
                advisory = (
                    "Heavy grazing detected - sparse ground cover in frequently "
                    "visited area. Consider rest period."
                )
                confidence = 0.6
                severity = "warning"
                pressure_level = "heavy"
            elif ground_cover <= 60:
                advisory = (
                    "Moderate grazing - ground cover thinning. Monitor recovery."
                )
                confidence = 0.5
                severity = "advisory"
                pressure_level = "moderate"
            else:
                # Dense tracks but cover still healthy — still moderate, but
                # fall through to the light band wording to avoid surprising
                # the user with a warning when the pasture is fine.
                advisory = (
                    "Moderate grazing - ground cover thinning. Monitor recovery."
                )
                confidence = 0.5
                severity = "advisory"
                pressure_level = "moderate"
        elif track_density >= 0.3:
            advisory = "Light to moderate grazing pressure."
            confidence = 0.4
            severity = "info"
            pressure_level = "light"
        else:
            advisory = "Minimal grazing pressure in this area."
            confidence = 0.5
            severity = "info"
            pressure_level = "minimal"

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "track_density": float(track_density),
                "ground_cover": float(ground_cover),
                "pressure_level": pressure_level,
            },
            severity=severity,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _no_data_result(self) -> AdaptationResult:
        """Build the standard 'no data' result."""
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory="No grazing data available.",
            confidence=0.0,
            data={
                "track_density": None,
                "ground_cover": None,
                "pressure_level": "unknown",
            },
            severity="info",
        )