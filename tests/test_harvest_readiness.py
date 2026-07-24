"""Tests for the HarvestReadiness adaptation module.

NOTE: These tests cover every advisory branch — no reading, all three factors
pass (confirmed), mature but moisture not ideal, mature but pH suboptimal, not
yet mature, the orange-specific maturity threshold, the readiness_score count,
and the disabled-module path. They use sys.path.insert(0, 'src') to import the
core and adaptation packages exactly as pyproject.toml's pythonpath setting
would, matching the convention used by every other test file in this project.

WHY: Harvest readiness is a season-critical go / wait decision. Calling it
wrong either wastes the season (harvesting immature fruit) or risks quality
loss (harvesting too late). Each branch must return the correct advisory,
confidence, severity, and data dict so the orchestrator and dashboard can act
on the result without re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.harvest_readiness import HarvestReadiness
from core.types import SensorReading, utc_now


def _reading(
    moisture: float | None = None,
    ph: float | None = None,
) -> SensorReading:
    """Helper: build a SensorReading with the given soil moisture and/or pH."""
    metrics: dict[str, float] = {}
    if moisture is not None:
        metrics["soil_moisture_pct"] = moisture
    if ph is not None:
        metrics["soil_pH"] = ph
    return SensorReading(
        sensor_name="soil_probe",
        timestamp=utc_now(),
        metrics=metrics,
        units={},
    )


class TestHarvestReadiness:
    """Tests for the HarvestReadiness adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert HarvestReadiness.name == "harvest_readiness"
        assert HarvestReadiness.category == "composite"
        assert "harvest readiness" in HarvestReadiness.description.lower()

    def test_all_factors_pass_confirmed(self):
        """All three factors pass → confirmed advisory, conf 0.7, info."""
        m = HarvestReadiness()
        result = m.analyze(
            _reading(moisture=50.0, ph=6.5),
            {"crop": "avocado", "days_since_flowering": 150},
        )
        assert result.module_name == "harvest_readiness"
        assert result.category == "composite"
        assert "confirmed" in result.advisory.lower()
        assert result.confidence == 0.7
        assert result.severity == "info"
        assert result.data["crop"] == "avocado"
        assert result.data["moisture_ok"] is True
        assert result.data["pH_ok"] is True
        assert result.data["days_ok"] is True
        assert result.data["maturity_days"] == 120
        assert result.data["readiness_score"] == 3

    def test_mature_but_moisture_not_ideal(self):
        """days_ok but moisture out of range → harvest soon, conf 0.5, advisory."""
        m = HarvestReadiness()
        result = m.analyze(
            _reading(moisture=15.0, ph=6.5),
            {"crop": "avocado", "days_since_flowering": 150},
        )
        assert "harvest soon" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["moisture_ok"] is False
        assert result.data["pH_ok"] is True
        assert result.data["days_ok"] is True
        assert result.data["readiness_score"] == 2

    def test_mature_but_ph_suboptimal(self):
        """days_ok and moisture ok but pH out of range → plan amendment, conf 0.5."""
        m = HarvestReadiness()
        result = m.analyze(
            _reading(moisture=50.0, ph=4.0),
            {"crop": "avocado", "days_since_flowering": 150},
        )
        assert "ph suboptimal" in result.advisory.lower()
        assert "amendment" in result.advisory.lower()
        assert result.confidence == 0.5
        assert result.severity == "advisory"
        assert result.data["moisture_ok"] is True
        assert result.data["pH_ok"] is False
        assert result.data["days_ok"] is True
        assert result.data["readiness_score"] == 2

    def test_not_yet_mature(self):
        """days_since_flowering below threshold → not mature, conf 0.6, info."""
        m = HarvestReadiness()
        result = m.analyze(
            _reading(moisture=50.0, ph=6.5),
            {"crop": "avocado", "days_since_flowering": 90},
        )
        assert "not yet mature" in result.advisory.lower()
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert result.data["days_ok"] is False
        assert result.data["maturity_days"] == 120
        assert "120" in result.advisory
        assert result.data["readiness_score"] == 2  # moisture + pH pass

    def test_no_reading_insufficient_data(self):
        """No reading at all → insufficient data, conf 0.0."""
        m = HarvestReadiness()
        result = m.analyze(None, {"crop": "avocado", "days_since_flowering": 150})
        assert "insufficient data" in result.advisory.lower()
        assert result.confidence == 0.0
        assert result.severity == "info"
        assert result.data["crop"] == "avocado"
        assert result.data["moisture_ok"] is False
        assert result.data["pH_ok"] is False
        assert result.data["days_ok"] is False
        assert result.data["readiness_score"] == 0

    def test_orange_maturity_threshold(self):
        """Orange requires 180 days (not 120) — 150 days is not mature."""
        m = HarvestReadiness()
        result = m.analyze(
            _reading(moisture=50.0, ph=6.5),
            {"crop": "orange", "days_since_flowering": 150},
        )
        # 150 days is enough for avocado (120) but not orange (180)
        assert result.data["maturity_days"] == 180
        assert result.data["days_ok"] is False
        assert "not yet mature" in result.advisory.lower()
        assert "180" in result.advisory
        assert result.confidence == 0.6

    def test_orange_mature_confirmed(self):
        """Orange with 200 days and good soil → confirmed readiness."""
        m = HarvestReadiness()
        result = m.analyze(
            _reading(moisture=55.0, ph=7.0),
            {"crop": "orange", "days_since_flowering": 200},
        )
        assert "confirmed" in result.advisory.lower()
        assert result.data["maturity_days"] == 180
        assert result.data["days_ok"] is True
        assert result.data["readiness_score"] == 3
        assert result.confidence == 0.7

    def test_readiness_score_partial(self):
        """Only one factor passes → readiness_score == 1."""
        m = HarvestReadiness()
        # days not ok, moisture not ok, pH ok
        result = m.analyze(
            _reading(moisture=80.0, ph=6.0),
            {"crop": "avocado", "days_since_flowering": 50},
        )
        # 50 days < 120 → days_ok False; moisture 80 > 70 → not ok; pH ok
        assert result.data["moisture_ok"] is False
        assert result.data["pH_ok"] is True
        assert result.data["days_ok"] is False
        assert result.data["readiness_score"] == 1
        # Not days_ok branch fires
        assert "not yet mature" in result.advisory.lower()

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = HarvestReadiness()
        m.set_enabled(False)
        result = m.process(
            _reading(moisture=50.0, ph=6.5),
            {"crop": "avocado", "days_since_flowering": 150},
        )
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0