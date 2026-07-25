"""Mock data manager for hardware-free sensor simulation.

NOTE: Generates realistic time-varying sensor data using random walk
with diurnal cycles for temperature, humidity, and light.

WHY: Allows development and testing on any machine without any physical
sensors attached. Every sensor's _read_mock() calls into MockManager.
"""

from __future__ import annotations

import math
import random
import threading
import time
from datetime import datetime, timezone


# Default baselines for Kenyan highlands agricultural context
_DEFAULT_BASELINES: dict[str, float] = {
    "soil_moisture_pct": 45.0,
    "soil_pH": 6.5,
    "lat": -1.2864,       # Near Nairobi
    "lon": 36.8222,
    "altitude_m": 1795.0,
    "temp_c": 24.0,
    "humidity_pct": 60.0,
    "light_lux": 15000.0,
    "accel_x": 0.0,
    "accel_y": 0.0,
    "accel_z": 9.81,
    # Cellular modem mock baselines
    "cellular_rssi_dbm": -75.0,       # decent 4G signal in mock
    "cellular_ber_pct": 0.5,          # low bit error rate
}

# Metrics that follow a diurnal (time-of-day) cycle
_DIURNAL_METRICS = {"temp_c", "humidity_pct", "light_lux"}

# Amplitude and phase for diurnal cycle (peak at ~14:00 local)
_DIURNAL_AMPLITUDE = {
    "temp_c": 6.0,         # ±6°C around baseline
    "humidity_pct": 15.0,  # ±15% around baseline
    "light_lux": 40000.0,  # large swing for day/night
}


class MockManager:
    """Generates realistic time-varying mock sensor data.

    Thread-safe. Each sensor should instantiate its own MockManager
    to maintain independent state.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._baselines = dict(_DEFAULT_BASELINES)
        self._state = dict(_DEFAULT_BASELINES)
        self._lock = threading.Lock()
        self._rng = random.Random(seed)

    def get(self, metric_name: str, jitter: float = 0.05) -> float:
        """Get a mock value for the given metric.

        Uses random walk around the baseline with optional jitter.
        Diurnal metrics (temp, humidity, light) follow a sine wave
        based on the current time of day.

        Args:
            metric_name: The metric to read (e.g. "soil_moisture_pct")
            jitter: Fraction of the baseline to randomize (0.0-1.0)

        Returns:
            A float value for the metric.
        """
        with self._lock:
            baseline = self._baselines.get(metric_name, 0.0)

            if metric_name in _DIURNAL_METRICS:
                value = self._diurnal_value(metric_name, baseline)
            else:
                # Random walk: drift the state slightly each call
                current = self._state.get(metric_name, baseline)
                drift = self._rng.gauss(0, abs(baseline) * 0.01 + 0.001)
                value = current + drift

            # Apply jitter
            if jitter > 0 and abs(value) > 0:
                value += self._rng.gauss(0, abs(value) * jitter)

            # Update state
            self._state[metric_name] = value

            return value

    def _diurnal_value(self, metric_name: str, baseline: float) -> float:
        """Calculate a value with a diurnal cycle."""
        now = datetime.now(timezone.utc)
        # Hours since midnight (use local approximation — Kenya is UTC+3)
        local_hour = (now.hour + 3) % 24  # EAT = UTC+3
        # Phase: peak at 14:00 (2 PM)
        phase = (local_hour - 14.0) / 24.0 * 2 * math.pi
        amplitude = _DIURNAL_AMPLITUDE.get(metric_name, 0.0)
        # Light drops to near-zero at night
        if metric_name == "light_lux":
            # Cosine: 1 at 14:00, -1 at 02:00
            cycle = math.cos(phase)
            if cycle < 0:
                return max(0.5, baseline * 0.001)  # near-zero at night
            return baseline + amplitude * cycle
        else:
            cycle = math.cos(phase)
            return baseline + amplitude * cycle

    def set_baseline(self, metric: str, value: float) -> None:
        """Override the baseline for a specific metric."""
        with self._lock:
            self._baselines[metric] = value
            self._state[metric] = value

    def reset(self) -> None:
        """Reset all baselines and state to defaults."""
        with self._lock:
            self._baselines = dict(_DEFAULT_BASELINES)
            self._state = dict(_DEFAULT_BASELINES)

    def get_state(self) -> dict[str, float]:
        """Return a snapshot of current state (for testing)."""
        with self._lock:
            return dict(self._state)