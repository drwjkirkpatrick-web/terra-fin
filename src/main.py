"""Main orchestrator for the Terra-Fin Agent.

NOTE: This module wires together all sensors, the engine, recorder,
event bus, harvest modules, night mode, dashboard, and CLI.

Startup order: storage → sensors → engine → recorder → night mode →
dashboard → CLI
Shutdown order: CLI → dashboard → night mode → recorder → engine →
sensors → storage

WHY: Centralized lifecycle management ensures all components start and
stop in the correct order, preventing resource leaks and race conditions.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from core.config import MainConfig
from core.types import utc_now
from core.event_bus import EventBus
from core.recorder import Recorder
from core.engine import Engine
from core.dashboard import DashboardService
from core.cli import CLI
from core.adaptation_manager import AdaptationManager

logger = logging.getLogger(__name__)


class TerraFinAgent:
    """Main orchestrator for the agricultural walking stick agent."""

    def __init__(self, config: MainConfig | None = None) -> None:
        self._config = config or MainConfig()
        self._event_bus = EventBus()
        self._recorder = Recorder(self._config.storage_path)
        self._sensors: dict[str, Any] = {}
        self._harvest_modules: dict[str, Any] = {}
        self._night_mode: Any = None
        self._dashboard: DashboardService | None = None
        self._engine: Engine | None = None
        self._adaptation_manager: AdaptationManager | None = None
        self._cli: CLI | None = None
        self._running = False

    def _init_sensors(self) -> None:
        """Initialize all enabled sensors in mock mode."""
        from core.sensor_base import SensorBase

        # Try to import and initialize each sensor
        # All sensors default to mock_mode=True for safety
        sensor_specs = [
            ("soil_moisture", "sensors.soil_moisture", "SoilMoistureSensor",
             self._config.soil_moisture),
            ("soil_ph", "sensors.soil_ph", "SoilPHSensor",
             self._config.soil_ph),
            ("gps", "sensors.gps", "GPSSensor",
             self._config.gps),
            ("temp_humidity", "sensors.temp_humidity", "TempHumiditySensor",
             self._config.temp_humidity),
            ("light", "sensors.light_sensor", "LightSensor",
             self._config.light),
            ("imu", "sensors.imu", "IMUSensor",
             self._config.imu),
            ("cellular", "sensors.cellular", "CellularSensor",
             self._config.cellular),
        ]

        for name, module_path, class_name, sensor_config in sensor_specs:
            if not getattr(sensor_config, "enabled", True):
                continue
            try:
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                mock = getattr(sensor_config, "mock_mode", True)
                sensor = cls(config=sensor_config, mock_mode=mock)
                sensor.initialize()
                self._sensors[name] = sensor
                logger.info("Initialized sensor: %s", name)
            except Exception as e:
                logger.warning("Could not initialize %s: %s", name, e)

    def _init_harvest_modules(self) -> None:
        """Initialize harvest tracking modules."""
        module_specs = [
            ("avocado", "modules.avocado", "AvocadoHarvest"),
            ("orange", "modules.orange", "OrangeHarvest"),
            ("greens", "modules.greens", "GreensHarvest"),
        ]

        for name, module_path, class_name in module_specs:
            try:
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                self._harvest_modules[name] = cls()
                logger.info("Initialized harvest module: %s", name)
            except Exception as e:
                logger.warning("Could not initialize %s: %s", name, e)

    def _init_night_mode(self) -> None:
        """Initialize night mode sentinel if enabled."""
        if not self._config.night_mode.enabled:
            return
        try:
            from modules.night_mode import NightModeSentinel
            self._night_mode = NightModeSentinel(
                config=self._config.night_mode,
                sensors=self._sensors,
                event_bus=self._event_bus,
                recorder=self._recorder,
            )
            logger.info("Initialized night mode sentinel")
        except Exception as e:
            logger.warning("Could not initialize night mode: %s", e)

    def _init_dashboard(self) -> None:
        """Initialize dashboard if enabled."""
        self._dashboard = DashboardService(
            host=self._config.dashboard.host,
            port=self._config.dashboard.port,
        )

    def _init_engine(self) -> None:
        """Initialize the engine with all sensors."""
        self._engine = Engine(self._config, self._sensors)

    def start(self) -> None:
        """Start the agent. Initializes all components in order."""
        logger.info("Starting TerraFinAgent: %s", self._config.device_name)

        # 1. Storage
        self._recorder.init_db()
        logger.info("Storage initialized: %s", self._config.storage_path)

        # 2. Sensors
        self._init_sensors()

        # 3. Engine
        self._init_engine()

        # 4. Night mode
        self._init_night_mode()
        if self._night_mode is not None:
            self._night_mode.start()

        # 5. Harvest modules
        self._init_harvest_modules()

        # 6. Dashboard
        self._init_dashboard()
        if self._dashboard is not None:
            self._dashboard.start()

        # 7. Adaptation manager
        self._adaptation_manager = AdaptationManager()

        self._running = True
        logger.info("TerraFinAgent started successfully")

    def stop(self) -> None:
        """Stop the agent. Shuts down components in reverse order."""
        logger.info("Stopping TerraFinAgent")

        # 1. Dashboard
        if self._dashboard is not None:
            self._dashboard.stop()

        # 2. Night mode
        if self._night_mode is not None:
            self._night_mode.stop()

        # 3. Sensors
        for name, sensor in self._sensors.items():
            try:
                sensor.cleanup()
            except Exception as e:
                logger.warning("Error cleaning up %s: %s", name, e)

        # 4. Storage
        self._recorder.close()

        self._running = False
        logger.info("TerraFinAgent stopped")

    def run_cli(self) -> None:
        """Start the agent and enter the CLI loop."""
        self.start()
        self._cli = CLI(
            engine=self._engine,  # type: ignore[arg-type]
            recorder=self._recorder,
            harvest_modules=self._harvest_modules,
            adaptation_manager=self._adaptation_manager,
        )
        try:
            self._cli.start()
        finally:
            self.stop()

    def run_dashboard(self) -> None:
        """Start the agent and serve the dashboard."""
        self.start()
        try:
            import time
            while self._running:
                # Update dashboard state periodically
                if self._engine and self._dashboard:
                    self._dashboard.update_state(self._engine.get_summary())
                time.sleep(5.0)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def run_daemon(self) -> None:
        """Start the agent as a background daemon (no CLI)."""
        self.start()
        try:
            import time
            while self._running:
                if self._engine:
                    self._engine.read_all()
                time.sleep(self._config.gps.poll_interval_s)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def health_check(self) -> dict:
        """Return overall system health."""
        return {
            "device_name": self._config.device_name,
            "running": self._running,
            "sensors": {
                name: s.health_check() for name, s in self._sensors.items()
            },
            "harvest_modules": list(self._harvest_modules.keys()),
            "night_mode": self._night_mode is not None,
            "dashboard": self._dashboard is not None,
            "adaptation_modules": len(self._adaptation_manager.module_names) if self._adaptation_manager else 0,
            "timestamp": utc_now(),
        }


def main():
    """Entry point for running the agent."""
    import argparse

    parser = argparse.ArgumentParser(description="Terra-Fin Agent")
    parser.add_argument("--mock", action="store_true", default=True,
                        help="Run in mock mode (no hardware)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to YAML config file")
    parser.add_argument("--dashboard", action="store_true",
                        help="Start dashboard server")
    parser.add_argument("--daemon", action="store_true",
                        help="Run as background daemon")
    args = parser.parse_args()

    if args.config:
        config = MainConfig.from_yaml(args.config)
    else:
        config = MainConfig()

    agent = TerraFinAgent(config)

    if args.daemon:
        agent.run_daemon()
    elif args.dashboard:
        agent.run_dashboard()
    else:
        agent.run_cli()


if __name__ == "__main__":
    main()