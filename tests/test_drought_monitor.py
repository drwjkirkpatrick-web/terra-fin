"""Tests for the DroughtMonitor adaptation module.

NOTE: These tests exercise the full range of drought-advisory bands and the
trend-detection logic without any hardware. They feed synthetic
SensorReading objects with controlled ``soil_moisture_pct`` values so the
average and trend computations are deterministic.

WHY: Drought detection directly drives irrigation decisions — a false
"adequate" reading during an emerging drought could lose a crop. The
thresholds and trend logic must be pinned at their boundaries so the farmer
is warned at the right moment, neither too early nor too late.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.types import SensorReading, utc_now
from adaptation.drought_monitor import DroughtMonitor


def _reading(moisture: float) -> SensorReading:
    """Helper: build a SensorReading with a single soil_moisture_pct metric."""
    return SensorReading(
        sensor_name="soil_moisture",
        timestamp=utc_now(),
        metrics={"soil_moisture_pct": float(moisture)},
        units={"soil_moisture_pct": "%"},
    )


class TestDroughtMonitor:
    """Tests covering advisory bands, trend detection, and edge cases."""

    # ------------------------------------------------------------------
    # Advisory band tests
    # ------------------------------------------------------------------

    def test_severe_drought(self):
        """Average below 15 % → critical advisory, confidence 0.9."""
        m = DroughtMonitor()
        # Feed readings that average below 15 %.
        for pct in (10.0, 12.0, 8.0):
            m.process(_reading(pct), {})
        result = m.process(_reading(14.0), {})
        assert result.severity == "critical"
        assert result.confidence == 0.9
        assert "emergency irrigation" in result.advisory.lower()

    def test_developing_drought(self):
        """Average 15–25 % → warning advisory, confidence 0.7."""
        m = DroughtMonitor()
        for pct in (20.0, 18.0, 22.0, 19.0):
            m.process(_reading(pct), {})
        result = m.process(_reading(21.0), {})
        assert result.severity == "warning"
        assert result.confidence == 0.7
        assert "increase irrigation" in result.advisory.lower()

    def test_soil_drying_advisory_band(self):
        """Average 25–35 % → advisory severity, confidence 0.5."""
        m = DroughtMonitor()
        for pct in (30.0, 28.0, 32.0):
            m.process(_reading(pct), {})
        result = m.process(_reading(29.0), {})
        assert result.severity == "advisory"
        assert result.confidence == 0.5
        assert "monitor closely" in result.advisory.lower()

    def test_adequate_moisture(self):
        """Average 35–70 % → info severity, confidence 0.6."""
        m = DroughtMonitor()
        for pct in (50.0, 55.0, 45.0):
            m.process(_reading(pct), {})
        result = m.process(_reading(48.0), {})
        assert result.severity == "info"
        assert result.confidence == 0.6
        assert "adequate" in result.advisory.lower()

    def test_wet_soil(self):
        """Average above 70 % → info severity, confidence 0.7, no irrigation."""
        m = DroughtMonitor()
        for pct in (75.0, 80.0, 72.0):
            m.process(_reading(pct), {})
        result = m.process(_reading(78.0), {})
        assert result.severity == "info"
        assert result.confidence == 0.7
        assert "well-watered" in result.advisory.lower()

    # ------------------------------------------------------------------
    # No-reading tests
    # ------------------------------------------------------------------

    def test_no_reading(self):
        """Passing None → zero-confidence info with no-data advisory."""
        m = DroughtMonitor()
        result = m.process(None, {})
        assert result.confidence == 0.0
        assert result.severity == "info"
        assert "no soil moisture data" in result.advisory.lower()
        assert result.data["avg_moisture"] is None

    def test_missing_metric_treated_as_no_data(self):
        """A reading without soil_moisture_pct → treated as no data."""
        m = DroughtMonitor()
        reading = SensorReading("soil_moisture", utc_now(), {}, {})
        result = m.process(reading, {})
        assert result.confidence == 0.0
        assert "no soil moisture data" in result.advisory.lower()

    # ------------------------------------------------------------------
    # Trend detection tests
    # ------------------------------------------------------------------

    def test_drying_trend_suffix(self):
        """Consistently decreasing last 5 readings → '(trend: drying)' suffix."""
        m = DroughtMonitor()
        # Feed 5 strictly-decreasing readings that stay in the adequate band.
        # Average of [50, 45, 40, 36, 33] = 40.8 → adequate, but the last 5
        # are strictly decreasing so the drying suffix should appear.
        for pct in (50.0, 45.0, 40.0, 36.0, 33.0):
            m.process(_reading(pct), {})
        result = m.process(_reading(30.0), {})
        # 30.0 is now included; average ≈ 39.0 → still adequate band.
        # The last 5 readings are [40, 36, 33, 30] — wait, we need 5 in the
        # window.  Let's verify the suffix is present.
        assert "(trend: drying)" in result.advisory
        assert result.data["trend"] == "drying"

    def test_drying_trend_with_severe_drought(self):
        """Drying trend should append even in the critical band."""
        m = DroughtMonitor()
        for pct in (20.0, 16.0, 12.0, 10.0, 8.0):
            m.process(_reading(pct), {})
        result = m.process(_reading(5.0), {})
        assert result.severity == "critical"
        assert "(trend: drying)" in result.advisory

    def test_stable_trend_no_suffix(self):
        """Non-monotonic readings → no drying suffix."""
        m = DroughtMonitor()
        # Readings that fluctuate — not consistently decreasing.
        for pct in (50.0, 48.0, 52.0, 49.0, 51.0):
            m.process(_reading(pct), {})
        result = m.process(_reading(50.0), {})
        assert "(trend: drying)" not in result.advisory
        assert result.data["trend"] == "stable"

    # ------------------------------------------------------------------
    # Internal state / data-structure tests
    # ------------------------------------------------------------------

    def test_max_readings_cap(self):
        """Internal readings list must cap at 20 entries."""
        m = DroughtMonitor()
        for pct in range(25):
            m.process(_reading(float(pct)), {})
        # After 25 readings, only the last 20 should be retained.
        assert len(m._readings) == 20

    def test_data_dict_shape(self):
        """Result data must contain avg_moisture, trend, and reading_count."""
        m = DroughtMonitor()
        m.process(_reading(40.0), {})
        result = m.process(_reading(60.0), {})
        assert "avg_moisture" in result.data
        assert "trend" in result.data
        assert "reading_count" in result.data
        assert result.data["reading_count"] == 2
        assert result.data["avg_moisture"] == 50.0  # (40 + 60) / 2

    def test_module_identity(self):
        """Module exposes the correct name, category, and description."""
        m = DroughtMonitor()
        assert m.name == "drought_monitor"
        assert m.category == "soil"
        assert "drought" in m.description.lower()

    def test_health_check_after_processing(self):
        """health_check() should reflect processed results."""
        m = DroughtMonitor()
        m.process(_reading(40.0), {})
        hc = m.health_check()
        assert hc["name"] == "drought_monitor"
        assert hc["category"] == "soil"
        assert hc["enabled"] is True
        assert hc["history_count"] == 1
        assert hc["has_result"] is True