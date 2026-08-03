"""Wind estimator adaptation module.

Estimates wind conditions from walking-stick IMU sway patterns.

NOTE: This module uses the lateral acceleration of the walking stick as a
proxy for wind. It is an APPROXIMATION, not a real anemometer. The walking
stick sways in wind; more sway = more wind. The sway_magnitude is the
horizontal acceleration magnitude (sqrt(accel_x^2 + accel_y^2)) reported by
the IMU sensor. Thresholds (strong/moderate/calm) were chosen empirically
and should be calibrated per stick geometry and mounting position.

WHY: A walking-stick agent does not carry a dedicated anemometer, but it
does carry an IMU. Wind causes the stick to sway, and that sway is
measurable. Even a rough wind estimate lets the agent warn the operator to
secure loose harvest bins, avoid working under weak branches, or adjust
expectations for spray drift / fruit drop.
"""


import logging
import math

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class WindEstimator(AdaptationModule):
    """Estimate wind from IMU sway.

    name='wind_estimator', category='weather'.
    """

    name = "wind_estimator"
    category = "weather"
    description = "Estimates wind conditions from stick sway patterns"

    # Sway thresholds (m/s^2 of horizontal acceleration).
    # NOTE: These are empirical approximations, not calibrated wind speeds.
    _STRONG_SWAY = 3.0  # above this => strong wind
    _MODERATE_SWAY = 1.0  # above this => moderate wind, below => calm

    def analyze(self, reading, context):
        """Analyze an IMU reading to estimate wind.

        Extracts accel_x, accel_y from reading.metrics and computes the
        horizontal sway magnitude = sqrt(accel_x^2 + accel_y^2).
        """
        if reading is None:
            logger.debug("[%s] no reading provided", self.name)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No motion data for wind estimation.",
                confidence=0.0,
                data={},
                severity="info",
            )

        metrics = reading.metrics
        accel_x = metrics.get("accel_x")
        accel_y = metrics.get("accel_y")

        if accel_x is None or accel_y is None:
            logger.debug("[%s] reading missing accel_x/accel_y", self.name)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No motion data for wind estimation.",
                confidence=0.0,
                data={},
                severity="info",
            )

        try:
            ax = float(accel_x)
            ay = float(accel_y)
        except (TypeError, ValueError):
            logger.warning("[%s] non-numeric accel values: %r %r", self.name, accel_x, accel_y)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No motion data for wind estimation.",
                confidence=0.0,
                data={},
                severity="info",
            )

        sway = math.sqrt(ax * ax + ay * ay)

        if sway > self._STRONG_SWAY:
            wind_estimate = "strong"
            advisory = "Strong wind detected — secure loose harvest bins and check tree branches."
            confidence = 0.6
            severity = "warning"
        elif sway >= self._MODERATE_SWAY:
            wind_estimate = "moderate"
            advisory = "Moderate wind — normal conditions for field work."
            confidence = 0.5
            severity = "info"
        else:
            wind_estimate = "calm"
            advisory = "Calm conditions — minimal wind."
            confidence = 0.4
            severity = "info"

        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=advisory,
            confidence=confidence,
            data={
                "sway_magnitude": sway,
                "wind_estimate": wind_estimate,
            },
            severity=severity,
        )