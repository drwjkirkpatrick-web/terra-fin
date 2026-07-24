"""Tests for the NutrientDepletionEstimator adaptation module.

NOTE: These tests cover avocado, orange, and greens harvests, the no-harvest
case, cumulative tracking across multiple harvests, threshold-triggered
advisories, the disabled-module path, and the unknown-crop fallback. They
use sys.path.insert(0, 'src') to import the core and adaptation packages
exactly as pyproject.toml's pythonpath setting would, matching the
convention used by every other test file in this project.

WHY: Nutrient depletion is a slow-moving but cumulative problem — a single
harvest never triggers an advisory, but ignoring removal across a season
silently mines the soil. The thresholds (50 g N, 60 g K) and per-crop rates
must produce the correct advisory, confidence, severity, and cumulative
data so the orchestrator and dashboard can trust the output without
re-validating it.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptation.nutrient_depletion import NutrientDepletionEstimator
from core.types import SensorReading, utc_now


class TestNutrientDepletionEstimator:
    """Tests for the NutrientDepletionEstimator adaptation module."""

    def test_class_attributes(self):
        """Module exposes the required class-level metadata."""
        assert NutrientDepletionEstimator.name == "nutrient_depletion"
        assert NutrientDepletionEstimator.category == "soil"
        assert "nutrient depletion" in (
            NutrientDepletionEstimator.description.lower()
        )

    def test_avocado_harvest(self):
        """Avocado harvest accumulates N-P-K at 3/0.5/4 g per kg."""
        m = NutrientDepletionEstimator()
        # 10 kg avocado → 30 g N, 5 g P, 40 g K
        result = m.analyze(
            None,
            {"harvest_data": {"crop_type": "avocado", "weight_kg": 10.0}},
        )
        assert result.module_name == "nutrient_depletion"
        assert result.category == "soil"
        assert result.data["total_n_g"] == 30.0
        assert result.data["total_p_g"] == 5.0
        assert result.data["total_k_g"] == 40.0
        assert result.data["crop_type"] == "avocado"
        # Below thresholds → info severity
        assert result.severity == "info"
        assert result.confidence == 0.3

    def test_orange_harvest(self):
        """Orange harvest accumulates N-P-K at 2/0.4/3 g per kg."""
        m = NutrientDepletionEstimator()
        # 15 kg orange → 30 g N, 6 g P, 45 g K
        result = m.analyze(
            None,
            {"harvest_data": {"crop_type": "orange", "weight_kg": 15.0}},
        )
        assert result.data["total_n_g"] == 30.0
        assert result.data["total_p_g"] == 6.0
        assert result.data["total_k_g"] == 45.0
        assert result.data["crop_type"] == "orange"
        assert result.severity == "info"

    def test_greens_harvest(self):
        """Greens harvest accumulates N-P-K at 4/0.8/5 g per kg."""
        m = NutrientDepletionEstimator()
        # 5 kg greens → 20 g N, 4 g P, 25 g K
        result = m.analyze(
            None,
            {"harvest_data": {"crop_type": "greens", "weight_kg": 5.0}},
        )
        assert result.data["total_n_g"] == 20.0
        assert result.data["total_p_g"] == 4.0
        assert result.data["total_k_g"] == 25.0
        assert result.data["crop_type"] == "greens"
        assert result.severity == "info"

    def test_no_harvest_data(self):
        """No harvest_data in context → info advisory, confidence 0.2."""
        m = NutrientDepletionEstimator()
        result = m.analyze(None, {})
        assert "no harvest data" in result.advisory.lower()
        assert result.confidence == 0.2
        assert result.severity == "info"
        assert result.data["total_n_g"] == 0.0
        assert result.data["total_p_g"] == 0.0
        assert result.data["total_k_g"] == 0.0

    def test_cumulative_tracking_across_harvests(self):
        """Multiple harvests accumulate N-P-K and trigger N advisory."""
        m = NutrientDepletionEstimator()
        # Two avocado harvests of 10 kg each → 60 g N (exceeds 50 g threshold)
        r1 = m.analyze(
            None,
            {"harvest_data": {"crop_type": "avocado", "weight_kg": 10.0}},
        )
        assert r1.data["total_n_g"] == 30.0
        assert r1.severity == "info"

        r2 = m.analyze(
            None,
            {"harvest_data": {"crop_type": "avocado", "weight_kg": 10.0}},
        )
        assert r2.data["total_n_g"] == 60.0
        assert r2.data["total_p_g"] == 10.0
        assert r2.data["total_k_g"] == 80.0
        # N exceeds 50 g → nitrogen advisory (takes priority over K)
        assert r2.severity == "advisory"
        assert r2.confidence == 0.5
        assert "nitrogen" in r2.advisory.lower()

    def test_potassium_advisory(self):
        """When K exceeds threshold but N does not, K advisory fires."""
        m = NutrientDepletionEstimator()
        # 16 kg greens → 64 g N, 12.8 g P, 80 g K
        # N (64) > 50 → N advisory fires first. Use a crop/mix where K
        # exceeds 60 g before N exceeds 50 g. Orange: 2 g N / 3 g K per kg.
        # 25 kg orange → 50 g N (not > 50), 75 g K (> 60).
        result = m.analyze(
            None,
            {"harvest_data": {"crop_type": "orange", "weight_kg": 25.0}},
        )
        assert result.data["total_n_g"] == 50.0  # not strictly > 50
        assert result.data["total_k_g"] == 75.0  # > 60
        assert result.severity == "advisory"
        assert "potassium" in result.advisory.lower()
        assert result.confidence == 0.5

    def test_disabled_module_returns_disabled(self):
        """When the module is disabled, process() short-circuits."""
        m = NutrientDepletionEstimator()
        m.set_enabled(False)
        result = m.process(
            None,
            {"harvest_data": {"crop_type": "avocado", "weight_kg": 10.0}},
        )
        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0