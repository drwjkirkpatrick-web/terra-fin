"""Time-varying mock data generator (ESP32/MicroPython).

NOTE: Generates realistic diurnal cycles. Uses time module only.
"""

import math
import time

_TEMP_AMPLITUDE = 8.0
_TEMP_MEAN = 20.0
_HUMIDITY_AMPLITUDE = 20.0
_HUMIDITY_MEAN = 60.0
_NOISE_SCALE = 0.5


def _seconds_since_midnight():
    t = time.gmtime(time.time())
    return t[3] * 3600 + t[4] * 60 + t[5]


def _diurnal_phase():
    seconds = _seconds_since_midnight()
    return 2 * math.pi * seconds / 86400.0 - math.pi / 2


class MockManager:
    """Generates realistic mock sensor readings with diurnal cycles."""

    def __init__(self):
        self._seed = int(time.time()) % 10000
        self._walk_state = 0.0

    def temperature(self):
        phase = _diurnal_phase()
        diurnal = _TEMP_MEAN + _TEMP_AMPLITUDE * math.sin(phase)
        noise = (self._noise_hash() - 0.5) * _NOISE_SCALE
        return round(diurnal + noise, 2)

    def humidity(self):
        phase = _diurnal_phase()
        diurnal = _HUMIDITY_MEAN - _HUMIDITY_AMPLITUDE * math.sin(phase)
        noise = (self._noise_hash() - 0.5) * _NOISE_SCALE * 2
        return max(0.0, min(100.0, round(diurnal + noise, 2)))

    def light_lux(self):
        phase = _diurnal_phase()
        lux = max(0.0, 50000.0 * math.sin(phase))
        noise = (self._noise_hash() - 0.5) * 500.0
        return max(0.0, round(lux + noise, 2))

    def soil_moisture(self):
        self._walk_state += (self._noise_hash() - 0.5) * 0.5
        self._walk_state = max(-10.0, min(10.0, self._walk_state))
        base = 50.0 + self._walk_state
        return max(0.0, min(100.0, round(base, 2)))

    def soil_ph(self):
        return round(6.5 + (self._noise_hash() - 0.5) * 0.2, 2)

    def gps_lat(self):
        return round(-0.5 + (self._noise_hash() - 0.5) * 0.01, 6)

    def gps_lon(self):
        return round(36.8 + (self._noise_hash() - 0.5) * 0.01, 6)

    def imu_accel(self):
        return (
            round((self._noise_hash() - 0.5) * 0.2, 3),
            round((self._noise_hash() - 0.5) * 0.2, 3),
            round(9.81 + (self._noise_hash() - 0.5) * 0.1, 3),
        )

    def imu_gyro(self):
        return (
            round((self._noise_hash() - 0.5) * 0.1, 3),
            round((self._noise_hash() - 0.5) * 0.1, 3),
            round((self._noise_hash() - 0.5) * 0.1, 3),
        )

    def cellular_signal(self):
        return round(-75.0 + (self._noise_hash() - 0.5) * 20.0, 1)

    def _noise_hash(self):
        self._seed = (self._seed * 1103515245 + 12345) & 0x7FFFFFFF
        return (self._seed % 10000) / 10000.0
