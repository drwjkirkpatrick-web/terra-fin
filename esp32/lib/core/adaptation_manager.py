"""Adaptation manager -- orchestrates all 30 adaptation modules (ESP32/MicroPython).

NOTE: The AdaptationManager runs all adaptation modules on each poll cycle,
passing the current sensor reading and context to each module. Collects results
and provides aggregated advisories.
"""

import logging

from .adaptation_base import AdaptationModule, AdaptationResult
from .types import SensorReading, utc_now

logger = logging.getLogger(__name__)

_MODULE_SPECS = [
    ("rain_predictor", "adaptation.rain_predictor", "RainPredictor"),
    ("temperature_trend", "adaptation.temperature_trend", "TemperatureTrend"),
    ("humidity_comfort", "adaptation.humidity_comfort", "HumidityComfort"),
    ("wind_estimator", "adaptation.wind_estimator", "WindEstimator"),
    ("frost_alert", "adaptation.frost_alert", "FrostAlert"),
    ("drought_monitor", "adaptation.drought_monitor", "DroughtMonitor"),
    ("solar_radiation", "adaptation.solar_radiation", "SolarRadiation"),
    ("growing_degree_days", "adaptation.growing_degree_days", "GrowingDegreeDays"),
    ("et_estimator", "adaptation.et_estimator", "EvapotranspirationEstimator"),
    ("soil_moisture_trend", "adaptation.soil_moisture_trend", "SoilMoistureTrend"),
    ("ph_drift_tracker", "adaptation.ph_drift_tracker", "PHDriftTracker"),
    ("nutrient_depletion", "adaptation.nutrient_depletion", "NutrientDepletionEstimator"),
    ("compaction_detector", "adaptation.compaction_detector", "CompactionDetector"),
    ("erosion_risk", "adaptation.erosion_risk", "ErosionRisk"),
    ("irrigation_scheduler", "adaptation.irrigation_scheduler", "IrrigationScheduler"),
    ("soil_temp_tracker", "adaptation.soil_temp_tracker", "SoilTempTracker"),
    ("mulch_advisor", "adaptation.mulch_advisor", "MulchAdvisor"),
    ("cover_crop_advisor", "adaptation.cover_crop_advisor", "CoverCropAdvisor"),
    ("compost_timing", "adaptation.compost_timing", "CompostTiming"),
    ("pest_pressure", "adaptation.pest_pressure", "PestPressure"),
    ("pollinator_activity", "adaptation.pollinator_activity", "PollinatorActivity"),
    ("bird_scavenger", "adaptation.bird_scavenger", "BirdScavengerMonitor"),
    ("insect_phenology", "adaptation.insect_phenology", "InsectPhenology"),
    ("beneficial_insects", "adaptation.beneficial_insects", "BeneficialInsectIndex"),
    ("grazing_pressure", "adaptation.grazing_pressure", "GrazingPressure"),
    ("rodent_activity", "adaptation.rodent_activity", "RodentActivity"),
    ("snake_alert", "adaptation.snake_alert", "SnakeAlert"),
    ("livestock_proximity", "adaptation.livestock_proximity", "LivestockProximity"),
    ("crop_disease_risk", "adaptation.crop_disease_risk", "CropDiseaseRisk"),
    ("harvest_readiness", "adaptation.harvest_readiness", "HarvestReadiness"),
]


class AdaptationManager:
    """Manages all 30 adaptation modules."""

    def __init__(self):
        self._modules = {}
        self._results = {}

    def load_all(self):
        """Lazy-load all adaptation modules."""
        for name, module_path, class_name in _MODULE_SPECS:
            try:
                mod = __import__(module_path, fromlist=[class_name])
                cls = getattr(mod, class_name)
                self._modules[name] = cls()
                logger.info("Loaded adaptation module: %s", name)
            except Exception as e:
                logger.error("Failed to load %s: %s", name, e)

    def run_all(self, reading=None, context=None):
        """Run all loaded modules. Returns dict of name -> AdaptationResult."""
        ctx = context or {}
        for name, module in self._modules.items():
            try:
                self._results[name] = module.process(reading, ctx)
            except Exception as e:
                logger.error("Module %s process failed: %s", name, e)
                self._results[name] = AdaptationResult(
                    module_name=name, category="unknown",
                    timestamp=utc_now(), advisory="Process error: {}".format(e),
                    confidence=0.0, data={},
                )
        return dict(self._results)

    def get_advisories(self, min_confidence=0.0):
        """Return all advisories above a confidence threshold."""
        return [
            {"module": name, "advisory": r.advisory, "confidence": r.confidence, "severity": r.severity}
            for name, r in self._results.items()
            if r.confidence >= min_confidence
        ]

    def get_module(self, name):
        return self._modules.get(name)

    def health_check(self):
        return {
            name: module.health_check()
            for name, module in self._modules.items()
        }
