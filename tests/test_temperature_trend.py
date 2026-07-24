"""Tests for the TemperatureTrend adaptation module.

NOTE: Tests use sys.path.insert(0, 'src') so they run standalone without
relying on pytest's pythonpath config — matching the project convention
for subagent-authored test files.

WHY: Rapid temperature shifts are time-sensitive advisories. These tests
verify that the module correctly classifies rising, falling, stable, and
edge-case (no reading, first reading, missing metric) scenarios.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import SensorReading
from adaptation.temperature_trend import TemperatureTrend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reading(temp_c: float, timestamp: str) -> SensorReading:
    """Create a minimal SensorReading with a temperature metric."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=timestamp,
        metrics={"temp_c": temp_c, "humidity_pct": 50.0},
        units={"temp_c": "°C", "humidity_pct": "%"},
        metadata={},
    )


# Timestamps spaced 1 hour apart — convenient for rate calculations.
TS = [
    "2026-07-24T10:00:00Z",
    "2026-07-24T11:00:00Z",
    "2026-07-24T12:00:00Z",
    "2026-07-24T13:00:00Z",
    "2026-07-24T14:00:00Z",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_reading_returns_no_data_advisory():
    """When reading is None, advisory should say 'No temperature data.'."""
    mod = TemperatureTrend()
    result = mod.analyze(None, {})

    assert result.advisory == "No temperature data."
    assert result.confidence == 0.0
    assert result.data["current_temp"] is None
    assert result.data["trend"] == "unknown"


def test_first_reading_no_trend_yet():
    """First reading should report temperature but indicate trend is pending."""
    mod = TemperatureTrend()
    result = mod.analyze(make_reading(25.0, TS[0]), {})

    assert result.confidence == 0.0
    assert result.data["current_temp"] == 25.0
    assert result.data["trend"] == "unknown"
    assert "pending" in result.advisory.lower()


def test_stable_temperature():
    """Temperatures changing < 1°C over the window should be 'stable'."""
    mod = TemperatureTrend()
    # 22.0, 22.2, 22.4 — total delta 0.4°C over 2 hours, well within stable.
    mod.analyze(make_reading(22.0, TS[0]), {})
    mod.analyze(make_reading(22.2, TS[1]), {})
    result = mod.analyze(make_reading(22.4, TS[2]), {})

    assert result.data["trend"] == "stable"
    assert result.severity == "info"
    assert "stable" in result.advisory.lower()
    assert result.confidence == 0.5


def test_rising_temperature_triggers_advisory():
    """Rise > 3°C/hour should trigger irrigation advisory with severity 'advisory'."""
    mod = TemperatureTrend()
    # 20°C → 25°C in one hour = +5°C/hour, above the 3°C/hour threshold.
    mod.analyze(make_reading(20.0, TS[0]), {})
    result = mod.analyze(make_reading(25.0, TS[1]), {})

    assert result.data["trend"] == "rising"
    assert result.data["rate_of_change"] > 3.0
    assert result.severity == "advisory"
    assert result.confidence == 0.7
    assert "irrigation" in result.advisory.lower()


def test_falling_temperature_triggers_warning():
    """Drop > 2°C/hour should trigger harvest warning with severity 'warning'."""
    mod = TemperatureTrend()
    # 25°C → 20°C in one hour = -5°C/hour, magnitude above 2°C/hour threshold.
    mod.analyze(make_reading(25.0, TS[0]), {})
    result = mod.analyze(make_reading(20.0, TS[1]), {})

    assert result.data["trend"] == "falling"
    assert abs(result.data["rate_of_change"]) > 2.0
    assert result.severity == "warning"
    assert result.confidence == 0.8
    assert "harvest" in result.advisory.lower()


def test_multiple_readings_build_trend():
    """After several readings, the module should retain only the last 5."""
    mod = TemperatureTrend()
    # Feed 6 readings — only the last 5 should be stored.
    temps = [20.0, 20.5, 21.0, 21.5, 22.0, 22.5]
    for i, t in enumerate(temps):
        result = mod.analyze(make_reading(t, f"2026-07-24T1{i}:00:00Z"), {})

    # After 6 readings, internal store should be capped at 5.
    assert len(mod._readings) == 5
    assert mod._readings[0][1] == 20.5  # oldest retained
    assert mod._readings[-1][1] == 22.5  # newest retained

    # Trend should reflect the net change over the retained window.
    # 20.5 → 22.5 over 5 hours = 0.4°C/hour — rising but below 3°C threshold.
    assert result.data["trend"] == "rising"
    assert result.severity == "info"


def test_missing_temp_metric_treated_as_no_data():
    """A reading without temp_c should be treated as no temperature data."""
    mod = TemperatureTrend()
    reading = SensorReading(
        sensor_name="temp_humidity",
        timestamp=TS[0],
        metrics={"humidity_pct": 50.0},  # no temp_c
        units={"humidity_pct": "%"},
        metadata={},
    )
    result = mod.analyze(reading, {})

    assert result.advisory == "No temperature data."
    assert result.confidence == 0.0
    assert result.data["current_temp"] is None