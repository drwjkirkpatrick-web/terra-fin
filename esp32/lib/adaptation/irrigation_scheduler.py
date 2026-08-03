"""Irrigation scheduler adaptation module.

NOTE: This module is one of ~30 adaptation modules that inherit from
AdaptationModule. It recommends irrigation timing by combining the current
soil moisture reading with evapotranspiration (ET) demand and rain predictions,
giving the farmer a single actionable irrigation decision per poll.

WHY: Irrigation is the single most water-sensitive decision on a farm. Acting
on moisture alone ignores atmospheric demand (a dry, hot, windy day drains soil
faster than a cool, humid one) and upcoming rain (irrigating before a storm
wastes water and can waterlog roots). By fusing three signals — moisture, ET,
and rain forecast — the module avoids both over- and under-irrigation.
"""


import logging

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class IrrigationScheduler(AdaptationModule):
    """Recommends irrigation timing based on moisture, ET, and rain predictions.

    Decision matrix:
        - moisture < 25%, no rain  → warning: irrigate now, 10–15 mm
        - moisture 25–40%, no rain → advisory: irrigate within 24 hours
        - moisture 25–40%, rain   → info: delay irrigation, monitor
        - moisture 40–70%         → info: adequate, no irrigation now
        - moisture > 70%          → info: wet, skip irrigation
        - no reading              → info: no data for scheduling
    """

    name = "irrigation_scheduler"
    category = "soil"
    description = "Recommends irrigation timing based on moisture, ET, and weather predictions"

    #: Moisture thresholds (percent).
    _DRY_THRESHOLD = 25.0       # below this → irrigate now
    _MODERATE_LOW = 40.0         # 25–40 → getting dry
    _ADEQUATE_HIGH = 70.0         # 40–70 → adequate

    # ------------------------------------------------------------------
    # AdaptationModule interface
    # ------------------------------------------------------------------
    def analyze(self, reading, context):
        """Analyze soil moisture, ET, and rain forecast to schedule irrigation.

        Args:
            reading: Current SensorReading (may be None). Must contain
                ``soil_moisture_pct`` in ``metrics``.
            context: Dict with optional ``et_mm_day`` (float, default 0.0)
                and ``rain_predicted`` (bool, default False).

        Returns:
            AdaptationResult with advisory, confidence, severity, and data
            containing moisture, et_mm, rain_predicted, and recommendation.
        """
        et_mm_day = float(context.get("et_mm_day", 0.0))
        rain_predicted = bool(context.get("rain_predicted", False))

        # --- No reading or no soil moisture metric ---
        if reading is None:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="No soil moisture data for irrigation scheduling.",
                confidence=0.0,
                data={
                    "moisture": None,
                    "et_mm": et_mm_day,
                    "rain_predicted": rain_predicted,
                    "recommendation": "no_data",
                },
                severity="info",
            )

        moisture = reading.metrics.get("soil_moisture_pct")
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
                advisory="No soil moisture data for irrigation scheduling.",
                confidence=0.0,
                data={
                    "moisture": None,
                    "et_mm": et_mm_day,
                    "rain_predicted": rain_predicted,
                    "recommendation": "no_data",
                },
                severity="info",
            )

        # --- Decision matrix ---
        if moisture < self._DRY_THRESHOLD and not rain_predicted:
            advisory = "Irrigate now - soil dry and no rain predicted. Apply 10-15mm water."
            confidence = 0.8
            severity = "warning"
            recommendation = "irrigate_now"
        elif moisture < self._MODERATE_LOW and not rain_predicted:
            advisory = "Irrigate within 24 hours - soil getting dry."
            confidence = 0.6
            severity = "advisory"
            recommendation = "irrigate_24h"
        elif moisture < self._MODERATE_LOW and rain_predicted:
            advisory = "Soil drying but rain expected - delay irrigation and monitor."
            confidence = 0.5
            severity = "info"
            recommendation = "delay_monitor"
        elif moisture <= self._ADEQUATE_HIGH:
            advisory = "Soil moisture adequate - no irrigation needed now."
            confidence = 0.7
            severity = "info"
            recommendation = "no_irrigation"
        else:  # moisture > 70
            advisory = "Soil wet - skip irrigation."
            confidence = 0.8
            severity = "info"
            recommendation = "skip_irrigation"

        data = {

            "moisture": moisture,
            "et_mm": et_mm_day,
            "rain_predicted": rain_predicted,
            "recommendation": recommendation,
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