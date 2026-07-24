"""Central data aggregation and analysis engine.

NOTE: The Engine polls all enabled sensors, aggregates their readings,
and provides summary/trend data for the prompt handlers and dashboard.

WHY: Centralizing aggregation prevents each consumer (prompts, dashboard,
night mode) from each needing to know about individual sensors.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

from .config import MainConfig
from .sensor_base import SensorBase
from .types import SensorReading, GPSPosition, utc_now

logger = logging.getLogger(__name__)

# Max readings to keep in the rolling window (per sensor)
_MAX_HISTORY = 360  # 30 min at 5s intervals


class Engine:
    """Aggregates sensor data and provides analysis.

    Thread-safe via RLock (methods call each other internally).
    """

    def __init__(self, config: MainConfig, sensors: dict[str, SensorBase]) -> None:
        self._config = config
        self._sensors = sensors
        self._lock = threading.RLock()
        self._history: dict[str, deque[SensorReading]] = {}
        self._baselines: dict[str, float] = {}
        for name in sensors:
            self._history[name] = deque(maxlen=_MAX_HISTORY)

    def read_all(self) -> dict[str, SensorReading | None]:
        """Poll all enabled sensors. Returns dict of sensor_name -> reading."""
        results: dict[str, SensorReading | None] = {}
        with self._lock:
            for name, sensor in self._sensors.items():
                try:
                    reading = sensor.read()
                    results[name] = reading
                    if reading is not None:
                        self._history[name].append(reading)
                except Exception as e:
                    logger.error("Error reading %s: %s", name, e)
                    results[name] = None
        return results

    def get_summary(self) -> dict[str, Any]:
        """Return an aggregated summary of all sensor data."""
        with self._lock:
            readings = self.read_all()
            summary: dict[str, Any] = {
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
                        "healthy": self._sensors[name].is_healthy,
                    }

            # Cross-sensor derived values
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

    def get_trends(self, window_minutes: int = 30) -> dict[str, Any]:
        """Analyze trends over a time window."""
        with self._lock:
            trends: dict[str, Any] = {}
            now = datetime.now(timezone.utc)

            for name, history in self._history.items():
                if len(history) < 2:
                    continue

                # Get readings within the window
                window_readings: list[SensorReading] = []
                for r in history:
                    try:
                        ts = datetime.fromisoformat(r.timestamp.replace("Z", "+00:00"))
                        if (now - ts).total_seconds() <= window_minutes * 60:
                            window_readings.append(r)
                    except (ValueError, AttributeError):
                        continue

                if len(window_readings) < 2:
                    continue

                first = window_readings[0]
                last = window_readings[-1]

                sensor_trend: dict[str, Any] = {
                    "count": len(window_readings),
                    "first_timestamp": first.timestamp,
                    "last_timestamp": last.timestamp,
                }

                for metric in first.metrics:
                    first_val = first.metrics.get(metric, 0.0)
                    last_val = last.metrics.get(metric, 0.0)
                    delta = last_val - first_val
                    sensor_trend[f"{metric}_delta"] = round(delta, 4)
                    sensor_trend[f"{metric}_rate"] = round(
                        delta / max(len(window_readings), 1), 4
                    )

                # GPS position delta
                if name == "gps":
                    lat1 = first.metrics.get("lat", 0.0)
                    lon1 = first.metrics.get("lon", 0.0)
                    lat2 = last.metrics.get("lat", 0.0)
                    lon2 = last.metrics.get("lon", 0.0)
                    dist_km = self._haversine(lat1, lon1, lat2, lon2)
                    sensor_trend["distance_km"] = round(dist_km, 4)

                trends[name] = sensor_trend

            return trends

    def get_baselines(self) -> dict[str, float]:
        """Return current rolling-average baselines."""
        with self._lock:
            return dict(self._baselines)

    def update_baselines(self) -> None:
        """Recalculate rolling averages from history."""
        with self._lock:
            for name, history in self._history.items():
                if len(history) == 0:
                    continue
                # Average each metric
                metric_sums: dict[str, float] = {}
                for reading in history:
                    for metric, value in reading.metrics.items():
                        metric_sums[metric] = metric_sums.get(metric, 0.0) + value
                for metric, total in metric_sums.items():
                    self._baselines[f"{name}.{metric}"] = round(
                        total / len(history), 4
                    )

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two lat/lon points in km."""
        R = 6371.0  # Earth radius km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        return R * c