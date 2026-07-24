"""Adaptation manager — orchestrates all 30 adaptation modules.

NOTE: The AdaptationManager runs all adaptation modules on each poll cycle,
passing the current sensor reading and context (trends, time, harvest data)
to each module. It collects results and provides aggregated advisories.

WHY: Centralizing the adaptation loop ensures all modules get consistent
context and the orchestrator only needs one call site.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .adaptation_base import AdaptationModule, AdaptationResult
from .types import SensorReading, utc_now

logger = logging.getLogger(__name__)

# All 30 module import paths (module_name, import_path, class_name)
_MODULE_SPECS = [
    # Weather (10)
    ("rain_predictor", "adaptation.rain_predictor", "RainPredictor"),
    ("temperature_trend", "adaptation.temperature_trend", "TemperatureTrend"),
    ("humidity_comfort", "adaptation.humidity_comfort", "HumidityComfort"),
    ("wind_estimator", "adaptation.wind_estimator", "WindEstimator"),
    ("frost_alert", "adaptation.frost_alert", "FrostAlert"),
    ("drought_monitor", "adaptation.drought_monitor", "DroughtMonitor"),
    ("solar_radiation", "adaptation.solar_radiation", "SolarRadiation"),
    ("growing_degree_days", "adaptation.growing_degree_days", "GrowingDegreeDays"),
    ("et_estimator", "adaptation.et_estimator", "EvapotranspirationEstimator"),
    # Soil (10)
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
    # Animal/Insect (10)
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
    """Manages all adaptation modules — initializes, runs, and aggregates."""

    def __init__(self) -> None:
        self._modules: dict[str, AdaptationModule] = {}
        self._init_modules()

    def _init_modules(self) -> None:
        """Dynamically import and instantiate all adaptation modules."""
        import importlib

        for name, import_path, class_name in _MODULE_SPECS:
            try:
                mod = importlib.import_module(import_path)
                cls = getattr(mod, class_name)
                instance = cls()
                self._modules[name] = instance
                logger.debug("Loaded adaptation module: %s", name)
            except Exception as e:
                logger.warning("Could not load adaptation module %s: %s", name, e)

    def run_all(
        self,
        reading: SensorReading | None = None,
        context: dict | None = None,
    ) -> dict[str, AdaptationResult]:
        """Run all enabled adaptation modules. Returns dict of name -> result."""
        ctx = context or {}
        results: dict[str, AdaptationResult] = {}
        for name, module in self._modules.items():
            try:
                result = module.process(reading, ctx)
                results[name] = result
            except Exception as e:
                logger.error("Adaptation module %s failed: %s", name, e)
                results[name] = AdaptationResult(
                    module_name=name,
                    category="unknown",
                    timestamp=utc_now(),
                    advisory=f"Module error: {e}",
                    confidence=0.0,
                    data={},
                )
        return results

    def get_advisories(self, severity_filter: str | None = None) -> list[dict]:
        """Return all current advisories, optionally filtered by severity."""
        advisories = []
        for name, module in self._modules.items():
            result = module._last_result
            if result is None:
                continue
            if severity_filter and result.severity != severity_filter:
                continue
            advisories.append({
                "module": name,
                "category": result.category,
                "advisory": result.advisory,
                "confidence": result.confidence,
                "severity": result.severity,
            })
        return advisories

    def get_advisories_by_category(self, category: str) -> list[dict]:
        """Return advisories for a specific category (weather/soil/animal/insect/composite)."""
        advisories = []
        for name, module in self._modules.items():
            if module.category != category:
                continue
            result = module._last_result
            if result is None:
                continue
            advisories.append({
                "module": name,
                "advisory": result.advisory,
                "confidence": result.confidence,
                "severity": result.severity,
            })
        return advisories

    def get_warnings(self) -> list[dict]:
        """Return only warning and critical advisories."""
        return self.get_advisories_by_severity("warning") + self.get_advisories_by_severity("critical")

    def get_advisories_by_severity(self, severity: str) -> list[dict]:
        """Return advisories matching a specific severity."""
        return self.get_advisories(severity_filter=severity)

    def health_check(self) -> dict:
        """Return health status of all adaptation modules."""
        return {
            "total_modules": len(self._modules),
            "loaded": list(self._modules.keys()),
            "modules": {name: m.health_check() for name, m in self._modules.items()},
        }

    def get_module(self, name: str) -> AdaptationModule | None:
        """Get a specific module by name."""
        return self._modules.get(name)

    @property
    def module_names(self) -> list[str]:
        """Return list of loaded module names."""
        return list(self._modules.keys())