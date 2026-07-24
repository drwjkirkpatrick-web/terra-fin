"""Tests for the dashboard."""

import sys
import os
import time
import urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.dashboard import DashboardService, DashboardState


class TestDashboardState:
    def test_initial_state(self):
        ds = DashboardState()
        state = ds.get_state()
        assert "timestamp" in state or "sensors" in state

    def test_update(self):
        ds = DashboardState()
        ds.update({"timestamp": "2026-01-01T00:00:00Z", "sensors": {"x": 1}})
        state = ds.get_state()
        assert "2026-01-01" in state

    def test_update_history(self):
        ds = DashboardState()
        ds.update_history("soil_moisture", [{"v": 1.0}, {"v": 2.0}])
        h = ds.get_history("soil_moisture")
        assert "1.0" in h
        assert "2.0" in h

    def test_update_harvests(self):
        ds = DashboardState()
        ds.update_harvests("avocado", [{"count": 10}])
        h = ds.get_harvests("avocado")
        assert "10" in h

    def test_update_night_events(self):
        ds = DashboardState()
        ds.update_night_events([{"event_type": "motion"}])
        events = ds.get_night_events()
        assert "motion" in events

    def test_update_health(self):
        ds = DashboardState()
        ds.update_health({"sensors": {"gps": "OK"}})
        h = ds.get_health()
        assert "gps" in h

    def test_thread_safety(self):
        import threading
        ds = DashboardState()
        errors = []

        def worker():
            try:
                for i in range(100):
                    ds.update({"i": i})
                    ds.get_state()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0


class TestDashboardService:
    def test_start_stop(self):
        svc = DashboardService(host="127.0.0.1", port=9295)
        svc.start()
        time.sleep(0.2)

        # Test that we can access the dashboard
        try:
            response = urllib.request.urlopen("http://127.0.0.1:9295/")
            html = response.read().decode()
            assert "TerraFin Dashboard" in html
        finally:
            svc.stop()

    def test_api_state(self):
        svc = DashboardService(host="127.0.0.1", port=9296)
        svc.start()
        time.sleep(0.2)
        svc.update_state({"timestamp": "2026-01-01T00:00:00Z", "sensors": {}})
        try:
            response = urllib.request.urlopen("http://127.0.0.1:9296/api/state")
            data = response.read().decode()
            assert "2026-01-01" in data
        finally:
            svc.stop()

    def test_404(self):
        svc = DashboardService(host="127.0.0.1", port=9297)
        svc.start()
        time.sleep(0.2)
        try:
            import urllib.error
            try:
                urllib.request.urlopen("http://127.0.0.1:9297/nonexistent")
                assert False, "Should have raised 404"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            svc.stop()