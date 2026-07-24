"""Abstract sensor base class with mock-safe hardware fallback.

NOTE: This follows the SensorBase GPIO/ADC driver pattern from the
edge-deployment-workflows skill. Every sensor driver inherits from this
class and implements _read_hardware() and _init_hardware().

WHY: The base class handles error wrapping, health tracking, and mock
fallback so each sensor driver only needs to implement the hardware-specific
parts.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import Any

from .types import SensorReading

logger = logging.getLogger(__name__)


class SensorBase(ABC):
    """Abstract base class for all sensors.

    Subclasses must set these class attributes:
        name: str        — sensor identifier (e.g. "soil_moisture")
        metrics: list    — list of metric names this sensor produces
        bus_type: str    — "i2c", "serial", "adc", "gpio"
        description: str — human-readable description

    Subclasses must implement:
        _init_hardware() -> bool   — set up hardware, return True if ready
        _read_hardware() -> SensorReading | None  — read from real hardware

    Subclasses may override:
        _read_mock() -> SensorReading  — generate mock data (default: zeros)
        cleanup() -> None              — release hardware resources
    """

    name: str = "base"
    metrics: list[str] = []
    bus_type: str = "unknown"
    description: str = "base sensor"

    def __init__(self, mock_mode: bool = False) -> None:
        self._mock_mode = mock_mode
        self._initialized = False
        self._healthy = False
        self._lock = threading.Lock()
        self._last_reading: SensorReading | None = None

    def initialize(self) -> bool:
        """Initialize the sensor. Returns True if hardware is ready.

        If mock_mode is True, skips hardware init entirely.
        """
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

    @abstractmethod
    def _init_hardware(self) -> bool:
        """Set up hardware resources. Return True if successful."""
        ...

    def read(self) -> SensorReading | None:
        """Read from the sensor. Returns SensorReading or None on failure.

        Automatically falls back to mock mode if hardware read fails.
        """
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
                try:
                    return self._read_mock()
                except Exception:
                    return None

    @abstractmethod
    def _read_hardware(self) -> SensorReading | None:
        """Read from real hardware. Return None on expected failure."""
        ...

    def _read_mock(self) -> SensorReading:
        """Generate mock data. Override for realistic simulation.

        Default returns zeros for all declared metrics.
        """
        return SensorReading(
            sensor_name=self.name,
            timestamp="",
            metrics={m: 0.0 for m in self.metrics},
            units={},
            metadata={"source": "mock"},
        )

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def health_check(self) -> dict:
        """Return a health status dictionary."""
        return {
            "name": self.name,
            "bus_type": self.bus_type,
            "metrics": list(self.metrics),
            "description": self.description,
            "initialized": self._initialized,
            "healthy": self._healthy,
            "mock_mode": self._mock_mode,
        }

    def cleanup(self) -> None:
        """Release hardware resources. Override if needed."""
        pass