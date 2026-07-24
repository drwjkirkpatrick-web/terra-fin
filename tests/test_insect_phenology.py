"""Tests for the InsectPhenology adaptation module.

NOTE: These tests verify warm-day accumulation, cold-day zero accumulation,
multi-reading accumulation, the five pest development stages
(early/larval/pupal/adult/late), the no-reading path, and reset.  They use
``sys.path.insert`` so the tests run without installing the package —
matching the convention in every other test file in this project.

WHY: Pest GDD accumulation is stateful, so the tests must carefully control
call order and reset the module between independent scenarios to avoid
cross-test contamination.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from adaptation.insect_phenology import InsectPhenology
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
class TestWarmReadingAccumulation:
    def test_warm_reading_accumulates_pest_gdd(self):
        """A warm reading above the 10 °C base adds to the pest GDD total."""
        ip = InsectPhenology()
        result = ip.analyze(make_reading(25.0), {})

        assert result.module_name == "insect_phenology"
        assert result.category == "insect"
        assert result.data["pest_gdd"] == 15.0  # 25 - 10
        assert result.data["stage"] == "early"
        assert result.data["risk_level"] == "low"
        assert result.severity == "info"
        assert result.confidence == 0.4

    def test_advisory_mentions_early_development(self):
        """The advisory for the early stage should mention eggs and larvae."""
        ip = InsectPhenology()
        result = ip.analyze(make_reading(20.0), {})
        assert "early development" in result.advisory.lower()
        assert "Low crop damage" in result.advisory


class TestColdReadingNoAccumulation:
    def test_cold_reading_zero_accumulation(self):
        """Below the 10 °C base, GDD contribution is zero."""
        ip = InsectPhenology()
        result = ip.analyze(make_reading(5.0), {})

        assert result.data["pest_gdd"] == 0.0
        assert result.data["stage"] == "early"
        assert "below development base" in result.advisory.lower()
        assert result.severity == "info"

    def test_exactly_base_temp_zero_accumulation(self):
        """At exactly 10 °C (the base), max(0, 10 - 10) = 0 — no accumulation."""
        ip = InsectPhenology()
        result = ip.analyze(make_reading(10.0), {})
        assert result.data["pest_gdd"] == 0.0


class TestMultipleReadingsAccumulate:
    def test_three_warm_readings_accumulate(self):
        """Three consecutive warm readings should sum their contributions."""
        ip = InsectPhenology()
        # 15°C → 5 GDD, 20°C → 10 GDD, 25°C → 15 GDD → total 30
        ip.analyze(make_reading(15.0), {})
        ip.analyze(make_reading(20.0), {})
        result = ip.analyze(make_reading(25.0), {})

        assert result.data["pest_gdd"] == 30.0
        assert result.data["stage"] == "early"

    def test_cold_reading_preserves_total(self):
        """A cold reading after warm readings preserves the prior total unchanged."""
        ip = InsectPhenology()
        ip.analyze(make_reading(25.0), {})   # +15
        ip.analyze(make_reading(30.0), {})   # +20 → total 35
        result = ip.analyze(make_reading(2.0), {})  # cold, +0

        assert result.data["pest_gdd"] == 35.0
        assert "below development base" in result.advisory.lower()


class TestPestStages:
    def test_early_stage(self):
        """Total < 50 GDD → early stage (info, confidence 0.4)."""
        ip = InsectPhenology()
        # 25°C → 15 GDD; one call → 15 → early
        result = ip.analyze(make_reading(25.0), {})
        assert result.data["stage"] == "early"
        assert "early development" in result.advisory
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["risk_level"] == "low"

    def test_larval_stage(self):
        """Total 50–150 GDD → larval stage (advisory, confidence 0.5)."""
        ip = InsectPhenology()
        # 35°C → 25 GDD; 2 calls → 50 → larval
        ip.analyze(make_reading(35.0), {})   # +25 → total 25 (still early)
        result = ip.analyze(make_reading(35.0), {})  # +25 → total 50 → larval
        assert result.data["pest_gdd"] == 50.0
        assert result.data["stage"] == "larval"
        assert "larval stage" in result.advisory
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["risk_level"] == "moderate"

    def test_pupal_stage(self):
        """Total 150–300 GDD → pupal stage (advisory, confidence 0.5)."""
        ip = InsectPhenology()
        # 60°C → 50 GDD; 4 calls → 200 → pupal (150-300 band)
        for _ in range(4):
            ip.analyze(make_reading(60.0), {})
        result = ip.analyze(make_reading(60.0), {})  # 5th → 250 → pupal
        assert result.data["pest_gdd"] == 250.0
        assert result.data["stage"] == "pupal"
        assert "pupating" in result.advisory
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["risk_level"] == "moderate"

    def test_adult_stage(self):
        """Total 300–500 GDD → adult stage (warning, confidence 0.6)."""
        ip = InsectPhenology()
        # 60°C → 50 GDD; 7 calls → 350 → adult (300-500 band)
        for _ in range(7):
            ip.analyze(make_reading(60.0), {})
        result = ip.analyze(make_reading(60.0), {})  # 8th → 400 → adult
        assert result.data["pest_gdd"] == 400.0
        assert result.data["stage"] == "adult"
        assert "peak activity" in result.advisory
        assert result.confidence == 0.6
        assert result.severity == "warning"
        assert result.data["risk_level"] == "high"

    def test_late_stage(self):
        """Total > 500 GDD → late stage (info, confidence 0.4)."""
        ip = InsectPhenology()
        # 260°C → 250 GDD; 2 calls → 500 (boundary, adult), 3rd → 750 → late
        ip.analyze(make_reading(260.0), {})  # 250 → adult
        ip.analyze(make_reading(260.0), {})  # 500 → adult (boundary)
        result = ip.analyze(make_reading(260.0), {})  # 750 → late
        assert result.data["pest_gdd"] == 750.0
        assert result.data["stage"] == "late"
        assert "Late generation" in result.advisory
        assert result.confidence == 0.4
        assert result.severity == "info"
        assert result.data["risk_level"] == "low"


class TestNoReading:
    def test_none_reading_returns_zero_confidence(self):
        """Passing None as the reading should yield a no-data advisory."""
        ip = InsectPhenology()
        result = ip.analyze(None, {})

        assert result.confidence == 0.0
        assert "No temperature data" in result.advisory
        assert result.data["pest_gdd"] == 0.0
        assert result.severity == "info"

    def test_none_reading_preserves_existing_total(self):
        """A None reading must not corrupt the existing accumulated total."""
        ip = InsectPhenology()
        ip.analyze(make_reading(25.0), {})  # +15
        result = ip.analyze(None, {})
        assert result.data["pest_gdd"] == 15.0


class TestReset:
    def test_reset_clears_accumulator(self):
        """``reset()`` should zero out the pest GDD total for a fresh season."""
        ip = InsectPhenology()
        ip.analyze(make_reading(25.0), {})  # +15
        assert ip.pest_gdd == 15.0
        ip.reset()
        assert ip.pest_gdd == 0.0