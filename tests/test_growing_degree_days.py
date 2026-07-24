"""Tests for the GrowingDegreeDays adaptation module.

NOTE: These tests verify warm-day accumulation, cold-day zero accumulation,
multi-day accumulation, the four season stages (early/mid/peak/late), and the
no-reading path. They use ``sys.path.insert`` so the tests run without
installing the package — matching the convention in every other test file in
this project.

WHY: GDD accumulation is stateful, so the tests must carefully control call
order and reset the module between independent scenarios to avoid
cross-test contamination.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from adaptation.growing_degree_days import GrowingDegreeDays
from core.types import SensorReading, utc_now


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_reading(temp_c: float) -> SensorReading:
    """Build a minimal SensorReading with a single temperature metric."""
    return SensorReading(
        sensor_name="bme680",
        timestamp=utc_now(),
        metrics={"temp_c": temp_c},
        units={"temp_c": "°C"},
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
class TestWarmDayAccumulation:
    def test_warm_day_accumulates_gdd(self):
        """A warm reading above the 10 °C base adds to the GDD total."""
        gdd = GrowingDegreeDays()
        result = gdd.analyze(make_reading(25.0), {})

        assert result.module_name == "growing_degree_days"
        assert result.category == "weather"
        assert result.data["gdd_today"] == 15.0  # 25 - 10
        assert result.data["gdd_total"] == 15.0
        assert result.data["stage"] == "early"
        assert result.severity == "info"

    def test_warm_day_advisory_mentions_gdd(self):
        """The advisory should mention the accumulated GDD value."""
        gdd = GrowingDegreeDays()
        result = gdd.analyze(make_reading(20.0), {})
        assert "GDD" in result.advisory
        assert "Early season" in result.advisory


class TestColdDayNoAccumulation:
    def test_cold_day_zero_accumulation(self):
        """Below the 10 °C base, GDD contribution is zero and a cold advisory is issued."""
        gdd = GrowingDegreeDays()
        result = gdd.analyze(make_reading(5.0), {})

        assert result.data["gdd_today"] == 0.0
        assert result.data["gdd_total"] == 0.0
        assert "Too cold" in result.advisory
        assert result.confidence == 0.4
        assert result.severity == "info"

    def test_exactly_base_temp_zero_accumulation(self):
        """At exactly 10 °C (the base), max(0, 10 - 10) = 0 — no accumulation."""
        gdd = GrowingDegreeDays()
        result = gdd.analyze(make_reading(10.0), {})

        assert result.data["gdd_today"] == 0.0
        assert result.data["gdd_total"] == 0.0


class TestMultipleDaysAccumulate:
    def test_three_warm_days_accumulate(self):
        """Three consecutive warm readings should sum their daily contributions."""
        gdd = GrowingDegreeDays()
        # 15°C → 5 GDD, 20°C → 10 GDD, 25°C → 15 GDD → total 30
        gdd.analyze(make_reading(15.0), {})
        gdd.analyze(make_reading(20.0), {})
        result = gdd.analyze(make_reading(25.0), {})

        assert result.data["gdd_today"] == 15.0
        assert result.data["gdd_total"] == 30.0
        assert result.data["stage"] == "early"

    def test_cold_day_does_not_add_but_preserves_total(self):
        """A cold reading after warm days preserves the prior total unchanged."""
        gdd = GrowingDegreeDays()
        gdd.analyze(make_reading(25.0), {})  # +15
        gdd.analyze(make_reading(30.0), {})  # +20 → total 35
        result = gdd.analyze(make_reading(2.0), {})  # cold, +0

        assert result.data["gdd_today"] == 0.0
        assert result.data["gdd_total"] == 35.0
        assert "Too cold" in result.advisory


class TestSeasonStages:
    def test_early_stage(self):
        """Total < 100 GDD → early stage."""
        gdd = GrowingDegreeDays()
        # 25°C → 15 GDD per call; one call → 15 → early
        result = gdd.analyze(make_reading(25.0), {})
        assert result.data["stage"] == "early"
        assert "Early season" in result.advisory
        assert result.confidence == 0.5

    def test_mid_stage(self):
        """Total 100–500 GDD → mid stage."""
        gdd = GrowingDegreeDays()
        # 35°C → 25 GDD per call; 5 calls → 125 → mid
        for _ in range(5):
            gdd.analyze(make_reading(35.0), {})
        result = gdd.analyze(make_reading(35.0), {})  # 6th call → 150
        assert result.data["gdd_total"] == 150.0
        assert result.data["stage"] == "mid"
        assert "Mid season" in result.advisory
        assert result.confidence == 0.6

    def test_peak_stage(self):
        """Total 500–1500 GDD → peak stage."""
        gdd = GrowingDegreeDays()
        # 100°C is unrealistic but we just need to cross thresholds fast.
        # Use 60°C → 50 GDD per call; 11 calls → 550 → peak
        for _ in range(11):
            gdd.analyze(make_reading(60.0), {})
        result = gdd.analyze(make_reading(60.0), {})  # 12th → 600
        assert result.data["gdd_total"] == 600.0
        assert result.data["stage"] == "peak"
        assert "Peak season" in result.advisory
        assert result.confidence == 0.7

    def test_late_stage(self):
        """Total > 1500 GDD → late stage."""
        gdd = GrowingDegreeDays()
        # 260°C → 250 GDD per call; 7 calls → 1750 → late
        for _ in range(7):
            gdd.analyze(make_reading(260.0), {})
        result = gdd.analyze(make_reading(260.0), {})  # 8th → 2000
        assert result.data["gdd_total"] == 2000.0
        assert result.data["stage"] == "late"
        assert "Late season" in result.advisory
        assert result.confidence == 0.6


class TestNoReading:
    def test_none_reading_returns_zero_confidence(self):
        """Passing None as the reading should yield a no-data advisory."""
        gdd = GrowingDegreeDays()
        result = gdd.analyze(None, {})

        assert result.confidence == 0.0
        assert "No temperature data" in result.advisory
        assert result.data["gdd_today"] == 0.0
        assert result.data["gdd_total"] == 0.0
        assert result.severity == "info"

    def test_none_reading_preserves_existing_total(self):
        """A None reading must not corrupt the existing accumulated total."""
        gdd = GrowingDegreeDays()
        gdd.analyze(make_reading(25.0), {})  # +15
        result = gdd.analyze(None, {})
        assert result.data["gdd_total"] == 15.0


class TestReset:
    def test_reset_clears_accumulator(self):
        """``reset()`` should zero out the GDD total for a fresh season."""
        gdd = GrowingDegreeDays()
        gdd.analyze(make_reading(25.0), {})  # +15
        assert gdd.gdd_total == 15.0
        gdd.reset()
        assert gdd.gdd_total == 0.0