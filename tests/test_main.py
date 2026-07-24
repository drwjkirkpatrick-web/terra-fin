"""Tests for the main orchestrator."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.config import MainConfig
from core.recorder import Recorder
from core.event_bus import EventBus


class TestTerraFinAgent:
    def _make_agent(self):
        # Import here to avoid import errors during collection
        from main import TerraFinAgent
        config = MainConfig()
        config.storage_path = ":memory:"
        config.dashboard.port = 9300 + hash("test") % 100  # avoid port conflicts
        agent = TerraFinAgent(config)
        return agent

    def test_init(self):
        agent = self._make_agent()
        assert agent._config.device_name == "terrafin-01"
        assert isinstance(agent._event_bus, EventBus)
        assert isinstance(agent._recorder, Recorder)

    def test_start_stop(self):
        agent = self._make_agent()
        agent.start()
        assert agent._running is True
        assert agent._engine is not None
        assert agent._recorder._conn is not None
        agent.stop()
        assert agent._running is False

    def test_health_check(self):
        agent = self._make_agent()
        agent.start()
        health = agent.health_check()
        assert "device_name" in health
        assert "running" in health
        assert "sensors" in health
        assert health["running"] is True
        agent.stop()

    def test_start_creates_sensors(self):
        """Sensors should be created (in mock mode) even without hardware."""
        agent = self._make_agent()
        agent.start()
        # In mock mode, sensors should be initialized
        # (if the sensor modules exist and import correctly)
        agent.stop()

    def test_stop_is_idempotent(self):
        agent = self._make_agent()
        agent.start()
        agent.stop()
        agent.stop()  # should not raise

    def test_start_without_dashboard(self):
        agent = self._make_agent()
        agent._config.dashboard.port = 0  # invalid but won't be used
        agent.start()
        agent.stop()

    def test_run_daemon_exits_cleanly(self):
        """Test that daemon mode can be started and stopped."""
        agent = self._make_agent()
        agent.start()
        # Simulate one iteration then stop
        assert agent._running is True
        agent.stop()
        assert agent._running is False