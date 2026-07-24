"""Tests for the CompactionDetector adaptation module.

NOTE: Tests use sys.path.insert(0, 'src') so they run standalone without
relying on pytest's pythonpath config — matching the project convention
for subagent-authored test files.

WHY: Compaction detection combines two signals (moisture + probe resistance)
that are easy to misinterpret in isolation.  These tests verify every branch
of the decision tree — wet/compacted, wet/no-compaction, dry/defer, moderate,
missing metric, and no reading — so advisories fire with the right
confidence and severity and the data dict carries the expected fields.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import SensorReading
from adaptation.compaction_detector import CompactionDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reading(moisture_pct: float, timestamp: str = "2026-07-24T10:00:00Z") -> SensorReading:
    """Create a minimal SensorReading with a soil moisture metric."""
    return SensorReading(
        sensor_name="soil_moisture",
        timestamp=timestamp,
        metrics={"soil_moisture_pct": moisture_pct},
        units={"soil_moisture_pct": "%"},
        metadata={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_reading_returns_no_data_advisory():
    """When reading is None, advisory should say 'No soil data...' and conf 0.0."""
    mod = CompactionDetector()
    result = mod.analyze(None, {})

    assert result.advisory == "No soil data for compaction assessment."
    assert result.confidence == 0.0
    assert result.severity == "info"
    assert result.data["moisture"] is None
    assert result.data["compaction_risk"] == "unknown"
    assert "resistance_estimate" in result.data


def test_missing_moisture_metric_treated_as_no_data():
    """A reading without soil_moisture_pct should be treated as no data."""
    mod = CompactionDetector()
    reading = SensorReading(
        sensor_name="soil_moisture",
        timestamp="2026-07-24T10:00:00Z",
        metrics={"temp_c": 25.0},  # no soil_moisture_pct
        units={"temp_c": "°C"},
        metadata={},
    )
    result = mod.analyze(reading, {})

    assert result.advisory == "No soil data for compaction assessment."
    assert result.confidence == 0.0
    assert result.data["moisture"] is None


def test_wet_high_resistance_compaction_likely():
    """moisture > 60% and resistance > 0.7 → compaction likely, advisory severity."""
    mod = CompactionDetector()
    result = mod.analyze(make_reading(65.0), {"probe_resistance": 0.8})

    assert "Soil compaction likely" in result.advisory
    assert result.confidence == 0.5
    assert result.severity == "advisory"
    assert result.data["moisture"] == 65.0
    assert result.data["resistance_estimate"] == 0.8
    assert result.data["compaction_risk"] == "high"


def test_wet_low_resistance_no_compaction():
    """moisture > 60% and resistance < 0.3 → no compaction, info severity."""
    mod = CompactionDetector()
    result = mod.analyze(make_reading(70.0), {"probe_resistance": 0.2})

    assert result.advisory == "Wet soil but low resistance - no compaction detected."
    assert result.confidence == 0.4
    assert result.severity == "info"
    assert result.data["compaction_risk"] == "low"


def test_dry_high_resistance_defer_assessment():
    """moisture < 30% and resistance > 0.5 → dry hard soil, defer assessment."""
    mod = CompactionDetector()
    result = mod.analyze(make_reading(20.0), {"probe_resistance": 0.6})

    assert "Dry hard soil" in result.advisory
    assert "Wait for moisture" in result.advisory
    assert result.confidence == 0.3
    assert result.severity == "info"
    assert result.data["compaction_risk"] == "moderate"


def test_moderate_moisture_is_inconclusive():
    """moisture between 30% and 60% → assessment inconclusive, low confidence."""
    mod = CompactionDetector()
    result = mod.analyze(make_reading(45.0), {"probe_resistance": 0.5})

    assert "inconclusive" in result.advisory.lower()
    assert result.confidence == 0.25
    assert result.severity == "info"
    assert result.data["compaction_risk"] == "unknown"


def test_default_probe_resistance_is_zero():
    """If context omits probe_resistance, resistance_estimate defaults to 0.0."""
    mod = CompactionDetector()
    # moisture > 60% with default resistance 0.0 → low resistance branch.
    result = mod.analyze(make_reading(80.0), {})

    assert result.data["resistance_estimate"] == 0.0
    assert result.advisory == "Wet soil but low resistance - no compaction detected."
    assert result.data["compaction_risk"] == "low"


def test_process_via_base_class_records_history():
    """The base class process() method should work and record history."""
    mod = CompactionDetector()
    mod.process(make_reading(65.0), {"probe_resistance": 0.8})
    mod.process(make_reading(70.0), {"probe_resistance": 0.2})

    history = mod.get_history()
    assert len(history) == 2
    assert history[-1]["module_name"] == "compaction_detector"
    assert history[-1]["category"] == "soil"
    assert mod.get_advisory() == "Wet soil but low resistance - no compaction detected."
    assert mod.health_check()["enabled"] is True