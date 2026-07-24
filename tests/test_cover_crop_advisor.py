"""Tests for the CoverCropAdvisor adaptation module.

NOTE: These tests exercise every decision branch in
CoverCropAdvisor.analyze — long rains (March–May), short rains
(October–December), dry season (January–February and June–September),
acidic soil supplement, very-dry soil supplement, the no-reading-no-month
insufficient-data path, and the disabled-module path via process().
They follow the same ``sys.path.insert(0, 'src')`` convention used by every
other test file in this project.

WHY: A cover crop recommendation that ignores season or soil condition can
waste seed and labour — legumes planted in the dry season will fail, and a
generic recommendation on acidic soil misses the opportunity to suggest
acid-tolerant species. Each branch must produce the exact advisory text,
confidence, and data dict the spec requires so downstream consumers (CLI,
dashboard, prompts) can trust the result.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.adaptation_base import AdaptationResult
from core.types import SensorReading, utc_now
from adaptation.cover_crop_advisor import CoverCropAdvisor


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _reading(ph: float, moisture: float) -> SensorReading:
    """Build a SensorReading with soil_pH and soil_moisture_pct metrics."""
    return SensorReading(
        sensor_name="soil_probe",
        timestamp=utc_now(),
        metrics={"soil_pH": ph, "soil_moisture_pct": moisture},
        units={"soil_pH": "pH", "soil_moisture_pct": "%"},
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

class TestCoverCropAdvisor:
    """Tests for the CoverCropAdvisor adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert CoverCropAdvisor.name == "cover_crop_advisor"
        assert CoverCropAdvisor.category == "soil"
        assert "cover crop" in CoverCropAdvisor.description.lower()

    def test_long_rains_season(self):
        """March–May → long rains legume recommendation, confidence 0.6."""
        m = CoverCropAdvisor()
        result = m.analyze(None, {"month": 4})
        assert result.module_name == "cover_crop_advisor"
        assert result.category == "soil"
        assert "long rains" in result.advisory.lower()
        assert "legumes" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.data["month"] == 4
        assert result.data["season"] == "long_rains"
        assert result.data["soil_pH"] is None
        assert result.data["moisture"] is None

    def test_short_rains_season(self):
        """October–December → short rains quick-growing recommendation, 0.5."""
        m = CoverCropAdvisor()
        result = m.analyze(None, {"month": 11})
        assert "short rains" in result.advisory.lower()
        assert "quick-growing" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.data["season"] == "short_rains"

    def test_dry_season(self):
        """January–February and June–September → drought-tolerant, 0.5."""
        m = CoverCropAdvisor()
        # Test a dry-month from each grouping (early-year and mid-year).
        for dry_month in (1, 2, 6, 9):
            m2 = CoverCropAdvisor()
            result = m2.analyze(None, {"month": dry_month})
            assert "dry season" in result.advisory.lower()
            assert "drought-tolerant" in result.advisory.lower()
            assert result.confidence == 0.5
            assert result.data["season"] == "dry"

    def test_acidic_soil_supplement(self):
        """pH < 5.5 with a reading → acidic-soil note appended."""
        m = CoverCropAdvisor()
        result = m.analyze(
            _reading(ph=5.0, moisture=40.0),
            {"month": 4},
        )
        assert "acidic" in result.advisory.lower()
        assert "lablab" in result.advisory.lower()
        assert result.data["soil_pH"] == 5.0
        assert result.data["moisture"] == 40.0
        # Still a long-rains recommendation at confidence 0.6.
        assert result.confidence == 0.6

    def test_very_dry_soil_supplement(self):
        """Moisture < 25 % with a reading → very-dry note appended."""
        m = CoverCropAdvisor()
        result = m.analyze(
            _reading(ph=6.5, moisture=15.0),
            {"month": 7},
        )
        assert "very dry" in result.advisory.lower()
        assert "drought-tolerant" in result.advisory.lower()
        assert result.data["soil_pH"] == 6.5
        assert result.data["moisture"] == 15.0
        assert result.confidence == 0.5

    def test_both_supplements(self):
        """Acidic AND very dry → both notes appended to the season rec."""
        m = CoverCropAdvisor()
        result = m.analyze(
            _reading(ph=5.2, moisture=20.0),
            {"month": 10},
        )
        assert "short rains" in result.advisory.lower()
        assert "acidic" in result.advisory.lower()
        assert "very dry" in result.advisory.lower()
        assert result.confidence == 0.5

    def test_no_data_insufficient(self):
        """No reading and no month → insufficient-data advisory, 0.0."""
        m = CoverCropAdvisor()
        result = m.analyze(None, {})
        assert "insufficient data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.data["month"] is None
        assert result.data["soil_pH"] is None
        assert result.data["moisture"] is None
        assert result.data["recommendation"] == (
            "Insufficient data for cover crop recommendation."
        )

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = CoverCropAdvisor()
        m.set_enabled(False)
        result = m.process(None, {"month": 4})
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0