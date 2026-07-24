"""Night mode sentinel — stationary monitoring during nighttime.

NOTE: When the walking stick is stationary at night, this module polls
the light sensor to detect night, then monitors the IMU for motion events
and GPS for position logging. All events are recorded and published to
the event bus.

WHY: A walking stick left standing in the orchard at night becomes a
sentinel — detecting intruders, animals, or environmental changes.
This is an awareness tool, not a security system.
"""

from __future__ import annotations

import logging
import math
import threading
from typing import Any

from core.types import NightEvent, GPSPosition, utc_now

logger = logging.getLogger(__name__)


class NightModeSentinel:
    """Monitors for motion and environmental events during nighttime.

    Thread-safe with threading.Event for graceful shutdown.
    """

    def __init__(
        self,
        config,  # NightModeConfig
        sensors: dict[str, Any],  # dict[str, SensorBase]
        event_bus: Any,  # EventBus
        recorder: Any,  # Recorder
    ) -> None:
        self._config = config
        self._sensors = sensors
        self._event_bus = event_bus
        self._recorder = recorder
        self._active = False
        self._running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._events: list[NightEvent] = []

    def start(self) -> None:
        """Start the night mode sentinel in a background thread."""
        with self._lock:
            if self._running:
                logger.warning("Night mode already running")
                return
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            logger.info("Night mode sentinel started")

    def stop(self) -> None:
        """Stop the night mode sentinel."""
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            self._running = False
            if self._thread is not None:
                self._thread.join(timeout=5.0)
                self._thread = None
            logger.info("Night mode sentinel stopped")

    def _poll_loop(self) -> None:
        """Main polling loop — runs until stopped."""
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as e:
                logger.error("Night mode poll error: %s", e)
            self._stop_event.wait(self._config.poll_interval_s)

    def _poll_once(self) -> None:
        """Execute one poll cycle."""
        # Check light level to determine if it's night
        light_sensor = self._sensors.get("light")
        if light_sensor is not None:
            light_reading = light_sensor.read()
            if light_reading is not None:
                lux = light_reading.metrics.get("light_lux", 0.0)
                is_night = lux < getattr(self._config, "night_lux_threshold", 10.0)

                if not is_night:
                    if self._active:
                        self._active = False
                        self._event_bus.publish("MODE_CHANGE", {
                            "mode": "day",
                            "timestamp": utc_now(),
                        })
                    return  # Not night, don't poll further

                if not self._active:
                    self._active = True
                    self._event_bus.publish("MODE_CHANGE", {
                        "mode": "night",
                        "timestamp": utc_now(),
                    })
        else:
            # No light sensor — assume night if we were started
            self._active = True

        # Night mode active — check IMU for motion
        imu_sensor = self._sensors.get("imu")
        if imu_sensor is not None and self._active:
            imu_reading = imu_sensor.read()
            if imu_reading is not None:
                ax = imu_reading.metrics.get("accel_x", 0.0)
                ay = imu_reading.metrics.get("accel_y", 0.0)
                az = imu_reading.metrics.get("accel_z", 0.0)
                mag = math.sqrt(ax**2 + ay**2 + az**2)
                motion_delta = abs(mag - 9.81)

                threshold = getattr(self._config, "motion_alert_threshold", 0.5)
                if motion_delta > threshold:
                    motion_class = self.classify_motion(motion_delta)
                    event = NightEvent(
                        event_type="motion",
                        timestamp=utc_now(),
                        description=f"Motion detected ({motion_class}, magnitude {motion_delta:.2f})",
                        severity="warning" if motion_class == "human" else "info",
                    )
                    self._record_event(event)

        # Log GPS position
        gps_sensor = self._sensors.get("gps")
        if gps_sensor is not None and self._active:
            gps_reading = gps_sensor.read()
            if gps_reading is not None:
                pos = GPSPosition(
                    lat=gps_reading.metrics.get("lat", 0.0),
                    lon=gps_reading.metrics.get("lon", 0.0),
                    altitude_m=gps_reading.metrics.get("altitude_m"),
                    timestamp=gps_reading.timestamp,
                    fix_quality=gps_reading.metadata.get("fix_quality", "unknown"),
                )
                try:
                    self._recorder.record_gps(pos)
                except Exception as e:
                    logger.error("Failed to record GPS: %s", e)

    def _record_event(self, event: NightEvent) -> None:
        """Record a night event internally and to the recorder."""
        with self._lock:
            self._events.append(event)
            # Keep only last 100 events
            if len(self._events) > 100:
                self._events = self._events[-100:]
        try:
            self._recorder.record_night_event(event)
        except Exception as e:
            logger.error("Failed to record night event: %s", e)
        self._event_bus.publish("NIGHT_ALERT", event.to_dict())

    def is_active(self) -> bool:
        """Return True if currently in night mode."""
        return self._active

    def get_events(self) -> list[NightEvent]:
        """Return recent night events."""
        with self._lock:
            return list(self._events)

    @staticmethod
    def classify_motion(accel_magnitude_delta: float) -> str:
        """Classify motion based on acceleration delta from gravity.

        NOTE: This is threshold-based and approximate. It cannot distinguish
        between animals and humans reliably — this is an awareness tool,
        not a security system.

        Args:
            accel_magnitude_delta: |accel_magnitude - gravity| in m/s²

        Returns:
            One of: "none", "small_animal", "human", "large_animal"
        """
        if accel_magnitude_delta < 0.3:
            return "none"
        elif accel_magnitude_delta < 1.0:
            return "small_animal"
        elif accel_magnitude_delta < 3.0:
            return "human"
        else:
            return "large_animal"