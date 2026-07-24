"""Tests for the IrrigationScheduler adaptation module.

NOTE: Tests use sys.path.insert(0, 'src') so they run standalone without
relying on pytest's pythonpath config — matching the project convention
for subagent-authored test files.

WHY: Irrigation timing is the most water-sensitive farm decision. These tests
verify each branch of the decision matrix — dry/irrigate-now, drying/no-rain,
drying/rain-expected, adequate, wet, and no-data — so the advisory fires at the
right moment and carries the right confidence and severity.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import SensorReading
from adaptation.irrigation_scheduler import IrrigationScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reading(moisture_pct: float) -> SensorReading:
    """Create a minimal SensorReading with a soil moisture metric."""
    return SensorReading(
        sensor_name="soil_moisture",
        timestamp="2026-07-24T12:00:00Z",
        metrics={"soil_moisture_pct": moisture_pct},
        units={"soil_moisture_pct": "%"},
        metadata={},
    )


# ---------------------------------------------------------------------------
# Tests — decision matrix branches
# ---------------------------------------------------------------------------

def test_dry_no_rain_triggers_warning():
    """moisture < 25% and no rain → warning, confidence 0.8, irrigate now."""
    mod = IrrigationScheduler()
    result = mod.analyze(make_reading(20.0), {"et_mm_day": 5.0, "rain_predicted": False})

    assert result.advisory == "Irrigate now - soil dry and no rain predicted. Apply 10-15mm water."
    assert result.confidence == 0.8
    assert result.severity == "warning"
    assert result.data["recommendation"] == "irrigate_now"
    assert result.data["moisture"] == 20.0
    assert result.data["et_mm"] == 5.0
    assert result.data["rain_predicted"] is False


def test_moderate_no_rain_triggers_advisory():
    """moisture 25–40% and no rain → advisory, confidence 0.6, irrigate within 24h."""
    mod = IrrigationScheduler()
    result = mod.analyze(make_reading(35.0), {"et_mm_day": 3.0, "rain_predicted": False})

    assert result.advisory == "Irrigate within 24 hours - soil getting dry."
    assert result.confidence == 0.6
    assert result.severity == "advisory"
    assert result.data["recommendation"] == "irrigate_24h"


def test_moderate_with_rain_delays_irrigation():
    """moisture 25–40% and rain predicted → info, confidence 0.5, delay & monitor."""
    mod = IrrigationScheduler()
    result = mod.analyze(make_reading(30.0), {"rain_predicted": True})

    assert result.advisory == "Soil drying but rain expected - delay irrigation and monitor."
    assert result.confidence == 0.5
    assert result.severity == "info"
    assert result.data["recommendation"] == "delay_monitor"
    assert result.data["rain_predicted"] is True


def test_adequate_moisture_no_irrigation():
    """moisture 40–70% → info, confidence 0.7, no irrigation needed."""
    mod = IrrigationScheduler()
    result = mod.analyze(make_reading(55.0), {})

    assert result.advisory == "Soil moisture adequate - no irrigation needed now."
    assert result.confidence == 0.7
    assert result.severity == "info"
    assert result.data["recommendation"] == "no_irrigation"


def test_wet_soil_skips_irrigation():
    """moisture > 70% → info, confidence 0.8, skip irrigation."""
    mod = IrrigationScheduler()
    result = mod.analyze(make_reading(85.0), {})

    assert result.advisory == "Soil wet - skip irrigation."
    assert result.confidence == 0.8
    assert result.severity == "info"
    assert result.data["recommendation"] == "skip_irrigation"


# ---------------------------------------------------------------------------
# Tests — no-data scenarios
# ---------------------------------------------------------------------------

def test_no_reading_returns_no_data_advisory():
    """When reading is None, advisory should say no soil moisture data."""
    mod = IrrigationScheduler()
    result = mod.analyze(None, {"et_mm_day": 4.0, "rain_predicted": True})

    assert result.advisory == "No soil moisture data for irrigation scheduling."
    assert result.confidence == 0.0
    assert result.severity == "info"
    assert result.data["moisture"] is None
    assert result.data["et_mm"] == 4.0
    assert result.data["rain_predicted"] is True
    assert result.data["recommendation"] == "no_data"


def test_missing_moisture_metric_treated_as_no_data():
    """A reading without soil_moisture_pct should be treated as no data."""
    mod = IrrigationScheduler()
    reading = SensorReading(
        sensor_name="soil_moisture",
        timestamp="2026-07-24T12:00:00Z",
        metrics={"temp_c": 25.0},  # no soil_moisture_pct
        units={"temp_c": "°C"},
        metadata={},
    )
    result = mod.analyze(reading, {})

    assert result.advisory == "No soil moisture data for irrigation scheduling."
    assert result.confidence == 0.0
    assert result.data["moisture"] is None
    assert result.data["recommendation"] == "no_data"


def test_process_via_base_class_records_history():
    """The base class process() method should work and record history."""
    mod = IrrigationScheduler()
    mod.process(make_reading(20.0), {"rain_predicted": False})
    mod.process(make_reading(55.0), {})

    history = mod.get_history()
    assert len(history) == 2
    assert history[-1]["severity"] == "info"
    assert (
        mod.get_advisory()
        == "Soil moisture adequate - no irrigation needed now."
    )


def test_default_context_values():
    """When context omits et_mm_day and rain_predicted, defaults are 0.0 and False."""
    mod = IrrigationScheduler()
    result = mod.analyze(make_reading(20.0), {})

    assert result.data["et_mm"] == 0.0
    assert result.data["rain_predicted"] is False
    assert result.severity == "warning"