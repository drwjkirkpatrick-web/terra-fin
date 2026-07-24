"""Tests for the SolarRadiation adaptation module.

NOTE: These tests pin all five lux classification bands, the no-reading path,
and the disabled-module path. They use ``sys.path.insert(0, 'src')`` to
import the core package exactly as pyproject.toml's ``pythonpath`` setting
would. No hardware is required — every test feeds a synthetic
SensorReading.

WHY: The lux thresholds drive shade-cloth advisories and growth-rate
expectations, so each band boundary must be pinned and tested. The
no-reading path guards the orchestrator's poll-when-sensor-unavailable
case, and the disabled path guards the base-class ``_enabled`` gate
that short-circuits ``analyze`` entirely.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.adaptation_base import AdaptationResult
from core.types import SensorReading, utc_now
from adaptation.solar_radiation import SolarRadiation


def _reading(lux: float) -> SensorReading:
    """Helper: build a minimal light SensorReading at the given lux."""
    return SensorReading(
        sensor_name="light",
        timestamp=utc_now(),
        metrics={"light_lux": lux},
        units={"light_lux": "lx"},
        metadata={"source": "test"},
    )


class TestSolarRadiation:
    def setup_method(self):
        """Fresh module instance for every test."""
        self.mod = SolarRadiation()

    # -- class attributes / shape ----------------------------------------- #

    def test_class_attributes(self):
        """Module identity should match the AdaptationModule contract."""
        assert self.mod.name == "solar_radiation"
        assert self.mod.category == "weather"
        assert "solar radiation" in self.mod.description.lower()
        assert "plant growth" in self.mod.description.lower()

    # -- very bright (> 80 000 lux) --------------------------------------- #

    def test_very_bright(self):
        """lux > 80000 → very_bright, advisory severity, shade-cloth hint."""
        result = self.mod.analyze(_reading(90_000.0), {})
        assert isinstance(result, AdaptationResult)
        assert result.module_name == "solar_radiation"
        assert result.category == "weather"
        assert result.severity == "advisory"
        assert result.confidence == 0.6
        assert "shade cloth" in result.advisory.lower()
        assert result.data["light_category"] == "very_bright"
        assert result.data["lux"] == 90_000.0
        assert result.data["estimated_w_per_m2"] > 0.0

    # -- full sun (40 000 – 80 000 lux) ------------------------------------ #

    def test_full_sun(self):
        """40 000 < lux <= 80 000 → full_sun, info, optimal photosynthesis."""
        result = self.mod.analyze(_reading(60_000.0), {})
        assert result.severity == "info"
        assert result.confidence == 0.7
        assert "optimal" in result.advisory.lower()
        assert result.data["light_category"] == "full_sun"
        assert result.data["lux"] == 60_000.0

    # -- overcast (10 000 – 40 000 lux) ------------------------------------ #

    def test_overcast(self):
        """10 000 < lux <= 40 000 → overcast, info, reduced light."""
        result = self.mod.analyze(_reading(25_000.0), {})
        assert result.severity == "info"
        assert result.confidence == 0.5
        assert "reduced" in result.advisory.lower()
        assert result.data["light_category"] == "overcast"
        assert result.data["lux"] == 25_000.0

    # -- dawn / dusk (500 – 10 000 lux) ----------------------------------- #

    def test_dawn_dusk(self):
        """500 < lux <= 10 000 → dawn_dusk, info, low light."""
        result = self.mod.analyze(_reading(3_000.0), {})
        assert result.severity == "info"
        assert result.confidence == 0.6
        assert "low light" in result.advisory.lower()
        assert result.data["light_category"] == "dawn_dusk"
        assert result.data["lux"] == 3_000.0

    # -- night (<= 500 lux) ----------------------------------------------- #

    def test_night(self):
        """lux <= 500 → night, info, no solar radiation."""
        result = self.mod.analyze(_reading(50.0), {})
        assert result.severity == "info"
        assert result.confidence == 0.8
        assert "night" in result.advisory.lower()
        assert result.data["light_category"] == "night"
        assert result.data["lux"] == 50.0
        assert result.data["estimated_w_per_m2"] >= 0.0

    # -- no reading ------------------------------------------------------- #

    def test_no_reading(self):
        """None reading → no_data, confidence 0.0, missing-data advisory."""
        result = self.mod.analyze(None, {})
        assert result.severity == "info"
        assert result.confidence == 0.0
        assert "no light data" in result.advisory.lower()
        assert result.data["light_category"] == "no_data"
        assert result.data["lux"] is None
        assert result.data["estimated_w_per_m2"] is None

    # -- disabled module -------------------------------------------------- #

    def test_disabled_module(self):
        """A disabled module should short-circuit via process(), not analyze."""
        self.mod.set_enabled(False)
        result = self.mod.process(_reading(60_000.0), {})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data == {}