"""Tests for the SoilMoistureTrend adaptation module.

NOTE: Tests use sys.path.insert(0, 'src') so they run standalone without
relying on pytest's pythonpath config — matching the project convention
for subagent-authored test files.

WHY: Irrigation timing is a time-sensitive decision for farmers. These tests
verify that the module correctly classifies dropping-fast, slowly-drying,
stable, increasing, insufficient-readings, and no-reading scenarios so the
advisory fires at the right moment — not too early, not too late.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import SensorReading
from adaptation.soil_moisture_trend import SoilMoistureTrend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reading(moisture_pct: float, timestamp: str) -> SensorReading:
    """Create a minimal SensorReading with a soil moisture metric."""
    return SensorReading(
        sensor_name="soil_moisture",
        timestamp=timestamp,
        metrics={"soil_moisture_pct": moisture_pct},
        units={"soil_moisture_pct": "%"},
        metadata={},
    )


# Timestamps spaced 1 hour apart — convenient for rate calculations.
TS = [
    "2026-07-24T10:00:00Z",
    "2026-07-24T11:00:00Z",
    "2026-07-24T12:00:00Z",
    "2026-07-24T13:00:00Z",
    "2026-07-24T14:00:00Z",
    "2026-07-24T15:00:00Z",
    "2026-07-24T16:00:00Z",
    "2026-07-24T17:00:00Z",
    "2026-07-24T18:00:00Z",
    "2026-07-24T19:00:00Z",
    "2026-07-24T20:00:00Z",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_reading_returns_no_data_advisory():
    """When reading is None, advisory should say 'No soil moisture data.'"""
    mod = SoilMoistureTrend()
    result = mod.analyze(None, {})

    assert result.advisory == "No soil moisture data."
    assert result.confidence == 0.0
    assert result.data["current_moisture"] is None
    assert result.data["trend_direction"] == "unknown"


def test_missing_moisture_metric_treated_as_no_data():
    """A reading without soil_moisture_pct should be treated as no data."""
    mod = SoilMoistureTrend()
    reading = SensorReading(
        sensor_name="soil_moisture",
        timestamp=TS[0],
        metrics={"temp_c": 25.0},  # no soil_moisture_pct
        units={"temp_c": "°C"},
        metadata={},
    )
    result = mod.analyze(reading, {})

    assert result.advisory == "No soil moisture data."
    assert result.confidence == 0.0
    assert result.data["current_moisture"] is None


def test_insufficient_readings_collects_baseline():
    """With fewer than 3 readings, advisory should request more baseline data."""
    mod = SoilMoistureTrend()
    result = mod.analyze(make_reading(50.0, TS[0]), {})

    assert "Collecting baseline" in result.advisory
    assert result.confidence == 0.2
    assert result.severity == "info"
    assert result.data["current_moisture"] == 50.0
    assert result.data["trend_direction"] == "unknown"

    # Two readings should still be insufficient.
    result2 = mod.analyze(make_reading(49.0, TS[1]), {})
    assert "Collecting baseline" in result2.advisory
    assert result2.confidence == 0.2


def test_dropping_fast_triggers_warning():
    """Rate < -2 %/hour should trigger warning with confidence 0.8."""
    mod = SoilMoistureTrend()
    # 50% → 45% → 40% over 2 hours = -5%/hour (well below -2).
    mod.analyze(make_reading(50.0, TS[0]), {})
    mod.analyze(make_reading(45.0, TS[1]), {})
    result = mod.analyze(make_reading(40.0, TS[2]), {})

    assert result.advisory == "Soil moisture dropping rapidly - irrigate within hours."
    assert result.confidence == 0.8
    assert result.severity == "warning"
    assert result.data["trend_direction"] == "dropping_fast"
    assert result.data["rate_of_change"] < -2.0


def test_slowly_drying_triggers_advisory():
    """Rate between -2 and -0.5 %/hour should trigger advisory, confidence 0.6."""
    mod = SoilMoistureTrend()
    # 50% → 49.2% → 48.5% over 2 hours = -0.75%/hour (between -2 and -0.5).
    mod.analyze(make_reading(50.0, TS[0]), {})
    mod.analyze(make_reading(49.2, TS[1]), {})
    result = mod.analyze(make_reading(48.5, TS[2]), {})

    assert result.advisory == "Soil slowly drying - plan irrigation within 1-2 days."
    assert result.confidence == 0.6
    assert result.severity == "advisory"
    assert result.data["trend_direction"] == "drying"
    assert -2.0 <= result.data["rate_of_change"] < -0.5


def test_stable_moisture():
    """Rate within ±0.5 %/hour should be stable, confidence 0.5, severity info."""
    mod = SoilMoistureTrend()
    # 50% → 50.1% → 50.05% over 2 hours ≈ +0.025%/hour — stable.
    mod.analyze(make_reading(50.0, TS[0]), {})
    mod.analyze(make_reading(50.1, TS[1]), {})
    result = mod.analyze(make_reading(50.05, TS[2]), {})

    assert result.severity == "info"
    assert result.confidence == 0.5
    assert result.data["trend_direction"] == "stable"
    assert "stable" in result.advisory.lower()
    assert abs(result.data["rate_of_change"]) <= 0.5


def test_increasing_moisture_skips_irrigation():
    """Rate > 0.5 %/hour should advise skipping irrigation, confidence 0.6."""
    mod = SoilMoistureTrend()
    # 40% → 42% → 45% over 2 hours = +2.5%/hour (well above 0.5).
    mod.analyze(make_reading(40.0, TS[0]), {})
    mod.analyze(make_reading(42.0, TS[1]), {})
    result = mod.analyze(make_reading(45.0, TS[2]), {})

    assert result.advisory == "Soil moisture increasing - skip irrigation."
    assert result.confidence == 0.6
    assert result.severity == "info"
    assert result.data["trend_direction"] == "increasing"
    assert result.data["rate_of_change"] > 0.5


def test_reading_buffer_capped_at_ten():
    """After more than 10 readings, only the last 10 should be retained."""
    mod = SoilMoistureTrend()
    # Feed 12 readings — only the last 10 should be stored.
    for i in range(12):
        result = mod.analyze(
            make_reading(50.0 + i * 0.1, f"2026-07-24T{10 + i:02d}:00:00Z"), {}
        )

    assert len(mod._readings) == 10
    # Oldest retained should be reading index 2 (i=2, moisture 50.2).
    assert mod._readings[0][1] == 50.2
    # Newest retained should be reading index 11 (i=11, moisture 51.1).
    assert mod._readings[-1][1] == 51.1


def test_process_via_base_class_records_history():
    """The base class process() method should work and record history."""
    mod = SoilMoistureTrend()
    mod.process(make_reading(50.0, TS[0]), {})
    mod.process(make_reading(45.0, TS[1]), {})
    mod.process(make_reading(40.0, TS[2]), {})

    history = mod.get_history()
    assert len(history) == 3
    assert history[-1]["severity"] == "warning"
    assert (
        mod.get_advisory()
        == "Soil moisture dropping rapidly - irrigate within hours."
    )