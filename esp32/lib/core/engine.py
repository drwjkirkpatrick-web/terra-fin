"""Central data aggregation and analysis engine (ESP32/MicroPython).

NOTE: The Engine polls all enabled sensors, aggregates their readings,
and provides summary/trend data. Uses simple lists instead of deque.
"""

import logging
import math
import time

try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

from .types import utc_now

logger = logging.getLogger(__name__)

_MAX_HISTORY = 200


def _make_lock():
    if hasattr(thread_mod, 'allocate_lock'):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()


class Engine:
    """Aggregates sensor data and provides analysis."""

    def __init__(self, config, sensors):
        self._config = config
        self._sensors = sensors
        self._lock = _make_lock()
        self._history = {}
        self._baselines = {}
        for name in sensors:
            self._history[name] = []

    def read_all(self):
        """Poll all enabled sensors. Returns dict of sensor_name -> reading."""
        results = {}
        with self._lock:
            for name, sensor in self._sensors.items():
                try:
                    reading = sensor.read()
                    results[name] = reading
                    if reading is not None:
                        self._history[name].append(reading)
                        if len(self._history[name]) > _MAX_HISTORY:
                            self._history[name] = self._history[name][-_MAX_HISTORY:]
                except Exception as e:
                    logger.error("Error reading %s: %s", name, e)
                    results[name] = None
        return results

    def get_summary(self):
        with self._lock:
            readings = self.read_all()
            summary = {
                "timestamp": utc_now(),
                "sensors": {},
                "cross_sensor": {},
            }
            for name, reading in readings.items():
                if reading is not None:
                    summary["sensors"][name] = {
                        "metrics": reading.metrics,
                        "units": reading.units,
                        "metadata": reading.metadata,
                        "healthy": getattr(self._sensors[name], 'is_healthy', False),
                    }
            light_reading = readings.get("light")
            if light_reading and "light_lux" in light_reading.metrics:
                summary["cross_sensor"]["is_day"] = light_reading.metrics["light_lux"] > 10.0
            imu_reading = readings.get("imu")
            if imu_reading:
                ax = imu_reading.metrics.get("accel_x", 0.0)
                ay = imu_reading.metrics.get("accel_y", 0.0)
                az = imu_reading.metrics.get("accel_z", 0.0)
                mag = math.sqrt(ax**2 + ay**2 + az**2)
                summary["cross_sensor"]["is_moving"] = abs(mag - 9.81) > 0.5
                summary["cross_sensor"]["accel_magnitude"] = round(mag, 2)
            gps_reading = readings.get("gps")
            if gps_reading:
                summary["cross_sensor"]["lat"] = gps_reading.metrics.get("lat")
                summary["cross_sensor"]["lon"] = gps_reading.metrics.get("lon")
            return summary

    def get_trends(self, window_minutes=30):
        with self._lock:
            trends = {}
            for name, history in self._history.items():
                if not history:
                    continue
                window = history[-360:] if len(history) > 360 else history
                if not window:
                    continue
                values = list(window[-1].metrics.keys())
                for metric in values:
                    vals = [r.metrics.get(metric) for r in window if metric in r.metrics]
                    vals = [v for v in vals if v is not None]
                    if len(vals) < 2:
                        continue
                    delta = vals[-1] - vals[0]
                    mean_val = sum(vals) / len(vals)
                    trends.setdefault(name, {})[metric] = {
                        "delta": round(delta, 3),
                        "mean": round(mean_val, 3),
                        "count": len(vals),
                    }
            return trends

    def get_history(self, sensor_name, limit=50):
        with self._lock:
            h = self._history.get(sensor_name, [])
            return [r.to_dict() for r in h[-limit:]]

    def get_baseline(self, sensor_name, metric):
        return self._baselines.get((sensor_name, metric))
