"""Terra-Fin Agent — ESP32/MicroPython entry point.

NOTE: This is the main script flashed to the ESP32. It initialises all
sensors, the engine, adaptation manager, recorder, dashboard, and CLI.
Falls back to mock mode when hardware is unavailable.

WHY: The ESP32 replaces the Pi Zero 2 W for cost and power efficiency.
This script bootstraps the full agent stack in mock-safe mode so it
can be developed and tested on a desktop before flashing.
"""

import logging
import sys
import time
import json

# --- Path setup for MicroPython ---
# On ESP32, lib/ is on sys.path. On CPython (tests), prepend it.
_lib_path = "/lib"
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

from core.config import MainConfig
from core.types import utc_now
from core.engine import Engine
from core.recorder import Recorder
from core.event_bus import EventBus
from core.adaptation_manager import AdaptationManager
from core.mock_manager import MockManager
from core.dashboard import DashboardState, DashboardServer

# Sensors (imported lazily with try/except for mock safety)
from sensors.soil_moisture import SoilMoistureSensor
from sensors.soil_ph import SoilPHSensor
from sensors.light_sensor import LightSensor
from sensors.temp_humidity import TempHumiditySensor
from sensors.gps import GPSSensor
from sensors.imu import IMUSensor
from sensors.cellular import CellularSensor

# Modules
from modules.avocado import AvocadoHarvest
from modules.orange import OrangeHarvest
from modules.greens import GreensHarvest
from modules.night_mode import NightModeSentinel

# CLI (optional — not needed on headless ESP32)
try:
    from core.cli import CLI
except ImportError:
    CLI = None

logger = logging.getLogger("terra-fin")


class TerraFinAgent:
    """Main agent orchestrator for the ESP32 walking stick."""

    def __init__(self, config=None):
        self._config = config or MainConfig()
        self._event_bus = EventBus()
        self._recorder = Recorder(self._config.storage_path)
        self._mock_mgr = MockManager()
        self._sensors = {}
        self._engine = None
        self._adapt_mgr = None
        self._dashboard_state = None
        self._dashboard_server = None
        self._night_sentinel = None
        self._harvest_modules = {}
        self._running = False

    def init(self):
        """Initialise all subsystems."""
        logger.info("Terra-Fin Agent initializing (mock_mode=%s)...",
                     self._config.mock_mode)

        # Init recorder storage
        try:
            self._recorder.init_db()
        except Exception as e:
            logger.warning("Recorder init failed (continuing): %s", e)

        # Init sensors
        self._init_sensors()

        # Init engine
        self._engine = Engine(self._config, self._sensors)

        # Init adaptation manager
        self._adapt_mgr = AdaptationManager()
        try:
            self._adapt_mgr.load_all()
            logger.info("Loaded %d adaptation modules",
                         len(self._adapt_mgr._modules))
        except Exception as e:
            logger.error("Adaptation manager load failed: %s", e)

        # Init harvest modules (JSON-backed, no DB needed)
        self._harvest_modules = {
            "avocado": AvocadoHarvest(),
            "orange": OrangeHarvest(),
            "greens": GreensHarvest(),
        }

        # Init night mode sentinel
        self._night_sentinel = NightModeSentinel(
            config=self._config.night_mode,
            sensors=self._sensors,
            event_bus=self._event_bus,
            recorder=self._recorder,
        )

        # Init dashboard
        if self._config.dashboard.enabled:
            self._dashboard_state = DashboardState()
            self._dashboard_server = DashboardServer(
                state=self._dashboard_state,
                port=self._config.dashboard.port,
                engine=self._engine,
            )

        logger.info("Terra-Fin Agent ready.")

    def _init_sensors(self):
        """Initialise all enabled sensors with mock-safe fallback."""
        sensor_classes = {
            "soil_moisture": (SoilMoistureSensor, self._config.soil_moisture),
            "soil_ph": (SoilPHSensor, self._config.soil_ph),
            "light": (LightSensor, self._config.light),
            "temp_humidity": (TempHumiditySensor, self._config.temp_humidity),
            "gps": (GPSSensor, self._config.gps),
            "imu": (IMUSensor, self._config.imu),
            "cellular": (CellularSensor, self._config.cellular),
        }

        for name, (cls, cfg) in sensor_classes.items():
            if not cfg.enabled:
                continue
            try:
                sensor = cls(cfg)
                self._sensors[name] = sensor
                logger.info("Sensor %s initialized", name)
            except Exception as e:
                logger.warning("Sensor %s init failed (mock): %s", name, e)

    def run_cycle(self):
        """Execute one full poll cycle: read sensors, run adaptations, update dashboard."""
        # Read all sensors
        readings = self._engine.read_all()

        # Run adaptation modules
        context = {
            "trends": self._engine.get_trends(),
            "timestamp": utc_now(),
        }
        advisories = self._adapt_mgr.run_all(
            reading=self._engine._history.get("soil_moisture", [None])[-1] if "soil_moisture" in self._engine._history else None,
            context=context,
        )

        # Record sensor readings
        for name, reading in readings.items():
            if reading is not None:
                try:
                    self._recorder.record_sensor(reading)
                except Exception as e:
                    logger.error("Record failed for %s: %s", name, e)

        # Update dashboard
        if self._dashboard_state:
            summary = self._engine.get_summary()
            self._dashboard_state.update(summary)
            self._dashboard_state.update_health(
                {name: {"healthy": getattr(s, "is_healthy", False)}
                 for name, s in self._sensors.items()}
            )

        return readings, advisories

    def start_dashboard(self):
        """Start the HTTP dashboard server."""
        if self._dashboard_server:
            try:
                self._dashboard_server.start()
                logger.info("Dashboard started on port %d",
                             self._config.dashboard.port)
            except Exception as e:
                logger.error("Dashboard start failed: %s", e)

    def start_night_mode(self):
        """Start the night mode sentinel."""
        if self._night_sentinel:
            self._night_sentinel.start()

    def stop_night_mode(self):
        """Stop the night mode sentinel."""
        if self._night_sentinel:
            self._night_sentinel.stop()

    def start_cli(self):
        """Start the interactive CLI (if available and on REPL)."""
        if CLI is None:
            logger.warning("CLI not available")
            return
        cli = CLI(self._engine, self._recorder)
        cli.start()

    def run(self, poll_interval=None):
        """Main loop — poll sensors and run adaptations indefinitely.

        Args:
            poll_interval: Seconds between poll cycles. Defaults to
                the shortest sensor poll interval.
        """
        self._running = True
        if poll_interval is None:
            # Use minimum sensor poll interval
            intervals = [
                getattr(s_cfg, "poll_interval_s", 5.0)
                for s_cfg in [
                    self._config.soil_moisture, self._config.soil_ph,
                    self._config.light, self._config.temp_humidity,
                    self._config.gps, self._config.imu,
                ]
            ]
            poll_interval = min(intervals) if intervals else 5.0

        logger.info("Starting main loop (poll_interval=%.1fs)", poll_interval)

        # Start dashboard
        self.start_dashboard()

        # Start night mode
        self.start_night_mode()

        while self._running:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error("Poll cycle error: %s", e)
            time.sleep(poll_interval)

    def stop(self):
        """Stop the agent."""
        self._running = False
        self.stop_night_mode()
        if self._dashboard_server:
            self._dashboard_server.stop()
        logger.info("Terra-Fin Agent stopped.")


def main():
    """Entry point — called on boot or from REPL."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    agent = TerraFinAgent()
    agent.init()

    # On ESP32 with USB REPL, offer CLI. On headless, run main loop.
    try:
        # Try to detect if we have a serial REPL (interactive mode)
        if sys.stdin.isatty():
            agent.start_cli()
        else:
            agent.run()
    except KeyboardInterrupt:
        agent.stop()
    except Exception as e:
        logger.error("Fatal: %s", e)
        agent.stop()
        raise


if __name__ == "__main__":
    main()