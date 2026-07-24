"""Tests for the SoilTempTracker adaptation module.

NOTE: Tests use sys.path.insert(0, 'src') so they run standalone without
relying on pytest's pythonpath config — matching the project convention
for subagent-authored test files.

WHY: Soil temperature drives germination timing and root health. These tests
verify all five temperature zones (very cold, cool, optimal, warm, too hot),
the context-vs-reading fallback logic, trend computation, buffer capping,
and the no-data path so advisories fire at the right soil temperature.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import SensorReading
from adaptation.soil_temp_tracker import SoilTempTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_reading(temp_c: float, timestamp: str) -> SensorReading:
    """Create a minimal SensorReading with an air-temp metric (proxy path)."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=timestamp,
        metrics={"temp_c": temp_c, "humidity_pct": 50.0},
        units={"temp_c": "°C", "humidity_pct": "%"},
        metadata={},
    )


# Timestamps spaced 1 hour apart — convenient for trend calculations.
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
    "2026-07-24T21:00:00Z",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_data_returns_no_data_advisory():
    """With no context soil_temp_c and no reading, advisory should be no-data."""
    mod = SoilTempTracker()
    result = mod.analyze(None, {})

    assert result.advisory == "No soil temperature data."
    assert result.confidence == 0.0
    assert result.data["soil_temp"] is None
    assert result.data["trend"] == "unknown"
    assert result.data["germination_outlook"] == "unknown"


def test_missing_both_context_and_metric_returns_no_data():
    """Reading present but no temp_c metric, and no context soil_temp_c → no data."""
    mod = SoilTempTracker()
    reading = SensorReading(
        sensor_name="soil_moisture",
        timestamp=TS[0],
        metrics={"soil_moisture_pct": 40.0},  # no temp_c
        units={"soil_moisture_pct": "%"},
        metadata={},
    )
    result = mod.analyze(reading, {})

    assert result.advisory == "No soil temperature data."
    assert result.confidence == 0.0
    assert result.data["soil_temp"] is None


def test_context_soil_temp_preferred_over_reading():
    """context['soil_temp_c'] should take priority over reading.metrics temp_c."""
    mod = SoilTempTracker()
    reading = make_reading(35.0, TS[0])  # air temp 35 — would be 'warm'
    result = mod.analyze(reading, {"soil_temp_c": 20.0})

    # 20°C is in the optimal zone (15–25), not the warm zone.
    assert result.data["soil_temp"] == 20.0
    assert result.data["germination_outlook"] == "optimal"
    assert result.severity == "info"
    assert result.confidence == 0.7
    assert "optimal" in result.advisory.lower()


def test_falls_back_to_reading_temp_c_as_proxy():
    """Without context soil_temp_c, reading.metrics temp_c should be used as proxy."""
    mod = SoilTempTracker()
    result = mod.analyze(make_reading(20.0, TS[0]), {})

    assert result.data["soil_temp"] == 20.0
    assert result.data["germination_outlook"] == "optimal"
    assert result.severity == "info"


def test_very_cold_soil_triggers_warning():
    """Soil temp < 5°C → warning, confidence 0.7, no-germination advisory."""
    mod = SoilTempTracker()
    result = mod.analyze(None, {"soil_temp_c": 2.0})

    assert result.advisory == (
        "Soil very cold - no germination expected. Wait for warming."
    )
    assert result.confidence == 0.7
    assert result.severity == "warning"
    assert result.data["germination_outlook"] == "none"


def test_cool_soil_info_advisory():
    """Soil temp 5–15°C → info, confidence 0.5, slow-germination advisory."""
    mod = SoilTempTracker()
    result = mod.analyze(None, {"soil_temp_c": 10.0})

    assert result.advisory == (
        "Soil cool - germination slow for most crops. "
        "Cold-tolerant greens may sprout."
    )
    assert result.confidence == 0.5
    assert result.severity == "info"
    assert result.data["germination_outlook"] == "slow"


def test_optimal_soil_info_advisory():
    """Soil temp 15–25°C → info, confidence 0.7, optimal advisory."""
    mod = SoilTempTracker()
    result = mod.analyze(None, {"soil_temp_c": 22.0})

    assert result.advisory == (
        "Soil temperature optimal for germination and root growth."
    )
    assert result.confidence == 0.7
    assert result.severity == "info"
    assert result.data["germination_outlook"] == "optimal"


def test_warm_soil_info_advisory():
    """Soil temp 25–35°C → info, confidence 0.5, tropical advisory."""
    mod = SoilTempTracker()
    result = mod.analyze(None, {"soil_temp_c": 28.0})

    assert result.advisory == "Soil warm - good for tropical crops. Monitor moisture."
    assert result.confidence == 0.5
    assert result.severity == "info"
    assert result.data["germination_outlook"] == "good_tropical"


def test_too_hot_soil_triggers_warning():
    """Soil temp > 35°C → warning, confidence 0.7, root-stress advisory."""
    mod = SoilTempTracker()
    result = mod.analyze(None, {"soil_temp_c": 40.0})

    assert result.advisory == "Soil too hot - root stress likely. Mulch to cool soil."
    assert result.confidence == 0.7
    assert result.severity == "warning"
    assert result.data["germination_outlook"] == "poor_heat_stress"


def test_trend_rising_after_multiple_readings():
    """Multiple increasing readings should produce trend 'rising'."""
    mod = SoilTempTracker()
    # 10 → 15 → 20 over 2 hours — delta 10°C, well above stable threshold.
    mod.analyze(None, {"soil_temp_c": 10.0})
    mod.analyze(None, {"soil_temp_c": 15.0})
    result = mod.analyze(None, {"soil_temp_c": 20.0})

    assert result.data["trend"] == "rising"
    assert result.data["soil_temp"] == 20.0


def test_trend_stable_when_change_is_small():
    """Readings within the stable threshold should be 'stable'."""
    mod = SoilTempTracker()
    # 20 → 20.2 → 20.4 — delta 0.4°C, below 1.0 stable threshold.
    mod.analyze(None, {"soil_temp_c": 20.0})
    mod.analyze(None, {"soil_temp_c": 20.2})
    result = mod.analyze(None, {"soil_temp_c": 20.4})

    assert result.data["trend"] == "stable"


def test_trend_falling():
    """Decreasing readings should produce trend 'falling'."""
    mod = SoilTempTracker()
    mod.analyze(None, {"soil_temp_c": 25.0})
    mod.analyze(None, {"soil_temp_c": 20.0})
    result = mod.analyze(None, {"soil_temp_c": 15.0})

    assert result.data["trend"] == "falling"


def test_reading_buffer_capped_at_ten():
    """After more than 10 readings, only the last 10 should be retained."""
    mod = SoilTempTracker()
    for i in range(12):
        mod.analyze(None, {"soil_temp_c": 15.0 + i * 0.5})

    assert len(mod._readings) == 10
    # Oldest retained is i=2 → 16.0, newest is i=11 → 20.5.
    assert mod._readings[0][1] == 16.0
    assert mod._readings[-1][1] == 20.5


def test_process_via_base_class_records_history():
    """The base class process() method should work and record history."""
    mod = SoilTempTracker()
    mod.process(None, {"soil_temp_c": 22.0})
    mod.process(None, {"soil_temp_c": 23.0})

    history = mod.get_history()
    assert len(history) == 2
    assert history[-1]["severity"] == "info"
    assert "optimal" in mod.get_advisory().lower()