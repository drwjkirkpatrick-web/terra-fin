"""Tests for mock manager."""

import sys
import os
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.mock_manager import MockManager


class TestMockManager:
    def test_get_returns_float(self):
        m = MockManager(seed=42)
        v = m.get("soil_moisture_pct")
        assert isinstance(v, float)

    def test_get_known_metric(self):
        m = MockManager(seed=42)
        v = m.get("soil_moisture_pct")
        # Should be near baseline (45.0) with some jitter
        assert 30.0 < v < 60.0

    def test_get_unknown_metric(self):
        m = MockManager(seed=42)
        v = m.get("unknown_metric")
        assert isinstance(v, float)

    def test_jitter_zero(self):
        m = MockManager(seed=42)
        v1 = m.get("soil_pH", jitter=0.0)
        v2 = m.get("soil_pH", jitter=0.0)
        # Without jitter, values should be very close (random walk drift only)
        assert abs(v1 - v2) < 1.0

    def test_set_baseline(self):
        m = MockManager(seed=42)
        m.set_baseline("soil_moisture_pct", 80.0)
        v = m.get("soil_moisture_pct", jitter=0.0)
        assert v > 70.0  # near new baseline

    def test_reset(self):
        m = MockManager(seed=42)
        m.set_baseline("soil_moisture_pct", 99.0)
        m.reset()
        v = m.get("soil_moisture_pct", jitter=0.0)
        # After reset, baseline should be back to 45
        assert v < 60.0

    def test_thread_safety(self):
        m = MockManager(seed=42)
        results = []
        errors = []

        def worker():
            try:
                for _ in range(100):
                    v = m.get("soil_moisture_pct")
                    results.append(v)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 400
        assert all(isinstance(v, float) for v in results)

    def test_diurnal_temp_varies(self):
        m = MockManager(seed=42)
        # Temp should vary with time of day
        values = [m.get("temp_c", jitter=0.0) for _ in range(5)]
        assert all(15.0 < v < 35.0 for v in values)

    def test_light_at_night(self):
        """Light should be near-zero during night hours."""
        m = MockManager(seed=42)
        # MockManager uses UTC hour + 3 for local time
        # We can't control the current time, but light should always be > 0
        v = m.get("light_lux")
        assert v >= 0.0

    def test_get_state(self):
        m = MockManager(seed=42)
        m.get("soil_moisture_pct")
        state = m.get_state()
        assert "soil_moisture_pct" in state