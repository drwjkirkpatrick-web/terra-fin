"""Thread-safe event bus for inter-module communication (ESP32/MicroPython).

NOTE: Uses _thread locks instead of threading. Lightweight pub/sub.
"""

import logging
import time

try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

logger = logging.getLogger(__name__)

EVENT_TYPES = [
    "SENSOR_READING",
    "NIGHT_ALERT",
    "HARVEST_LOGGED",
    "MODE_CHANGE",
    "GPS_FIX",
    "LOW_BATTERY",
]


def _make_lock():
    if hasattr(thread_mod, 'allocate_lock'):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()


class EventBus:
    """Thread-safe pub/sub event bus."""

    def __init__(self):
        self._subscribers = {}
        self._lock = _make_lock()
        self._counter = 0

    def subscribe(self, event_type, callback):
        sub_id = str(self._counter)
        self._counter += 1
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = {}
            self._subscribers[event_type][sub_id] = callback
        return sub_id

    def unsubscribe(self, sub_id):
        with self._lock:
            for event_type, subs in self._subscribers.items():
                if sub_id in subs:
                    del subs[sub_id]
                    return True
        return False

    def publish(self, event_type, data):
        notified = 0
        with self._lock:
            subs = {}
            if event_type in self._subscribers:
                subs = dict(self._subscribers[event_type])
        for sub_id, callback in subs.items():
            try:
                callback(data)
                notified += 1
            except Exception as e:
                logger.error("Subscriber %s failed on %s: %s", sub_id, event_type, e)
        return notified

    def subscriber_count(self, event_type):
        with self._lock:
            return len(self._subscribers.get(event_type, {}))

    def clear(self):
        with self._lock:
            self._subscribers.clear()
