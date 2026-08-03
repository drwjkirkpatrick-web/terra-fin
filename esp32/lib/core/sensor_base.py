"""Abstract sensor base class with mock-safe hardware fallback (ESP32/MicroPython).

NOTE: Uses _thread locks. Every sensor driver inherits from this class.
"""

import logging
import time

try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

from .types import SensorReading, utc_now

logger = logging.getLogger(__name__)


def _make_lock():
    if hasattr(thread_mod, 'allocate_lock'):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()


class SensorBase:
    """Abstract base class for all sensors.

    Subclasses must set: name, metrics, bus_type, description
    Subclasses must implement: _init_hardware() -> bool, _read_hardware() -> SensorReading or None
    """

    name = "base"
    metrics = []
    bus_type = "unknown"
    description = "base sensor"

    def __init__(self, config=None, mock_mode=False):
        self._config = config
        self._mock_mode = mock_mode
        self._initialized = False
        self._healthy = False
        self._lock = _make_lock()
        self._last_reading = None

    def initialize(self):
        """Initialize the sensor. Returns True if hardware is ready."""
        if self._mock_mode:
            logger.info("[%s] running in mock mode", self.name)
            self._initialized = True
            return True
        try:
            result = self._init_hardware()
            self._initialized = result
            if not result:
                logger.warning("[%s] hardware init failed, falling back to mock", self.name)
                self._mock_mode = True
            return result
        except Exception as e:
            logger.error("[%s] hardware init exception: %s", self.name, e)
            self._mock_mode = True
            self._initialized = True
            return False

    def _init_hardware(self):
        """Set up hardware resources. Return True if successful."""
        raise NotImplementedError

    def read(self):
        """Read from the sensor. Returns SensorReading or None."""
        with self._lock:
            try:
                if self._mock_mode or not self._initialized:
                    reading = self._read_mock()
                else:
                    reading = self._read_hardware()
                    if reading is None:
                        logger.warning("[%s] hardware read returned None, using mock", self.name)
                        reading = self._read_mock()
                if reading is not None:
                    self._last_reading = reading
                    self._healthy = True
                return reading
            except Exception as e:
                logger.error("[%s] read failed: %s", self.name, e)
                self._healthy = False
                reading = self._read_mock()
                if reading is not None:
                    self._last_reading = reading
                return reading

    def _read_hardware(self):
        """Read from real hardware. Must return SensorReading or None."""
        raise NotImplementedError

    def _read_mock(self):
        """Generate mock data. Default: all metrics = 0.0."""
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={m: 0.0 for m in self.metrics},
            units={},
            metadata={"mock": True},
        )

    @property
    def is_healthy(self):
        return self._healthy

    def get_last_reading(self):
        return self._last_reading

    def cleanup(self):
        """Release hardware resources. Override in subclass if needed."""
        pass
