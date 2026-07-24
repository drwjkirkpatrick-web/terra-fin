"""Thread-safe event bus for inter-module communication.

NOTE: Uses threading (not asyncio) for Pi Zero simplicity.
The event bus is a lightweight pub/sub — modules subscribe to event types
and get notified when events are published.

WHY: Decouples modules — the night mode sentinel can emit NIGHT_ALERT
events without knowing who listens. The recorder listens without knowing
who emits.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Callable

logger = logging.getLogger(__name__)


# Known event types
EVENT_TYPES = [
    "SENSOR_READING",
    "NIGHT_ALERT",
    "HARVEST_LOGGED",
    "MODE_CHANGE",
    "GPS_FIX",
    "LOW_BATTERY",
]


class EventBus:
    """Thread-safe pub/sub event bus.

    Subscribers are callbacks that receive a dict of event data.
    Callback exceptions are caught and logged — one bad subscriber
    does not break the bus.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, dict[str, Callable]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, callback: Callable) -> str:
        """Subscribe to an event type. Returns a subscription ID."""
        sub_id = str(uuid.uuid4())
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = {}
            self._subscribers[event_type][sub_id] = callback
        logger.debug("Subscribed %s to %s", sub_id, event_type)
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """Unsubscribe by subscription ID. Returns True if found."""
        with self._lock:
            for event_type, subs in self._subscribers.items():
                if sub_id in subs:
                    del subs[sub_id]
                    logger.debug("Unsubscribed %s from %s", sub_id, event_type)
                    return True
            return False

    def publish(self, event_type: str, data: dict) -> int:
        """Publish an event. Returns the number of subscribers notified."""
        notified = 0
        with self._lock:
            subs = dict(self._subscribers.get(event_type, {}))

        for sub_id, callback in subs.items():
            try:
                callback(data)
                notified += 1
            except Exception as e:
                logger.error("Subscriber %s failed on %s: %s", sub_id, event_type, e)

        logger.debug("Published %s to %d subscribers", event_type, notified)
        return notified

    def subscriber_count(self, event_type: str) -> int:
        """Return the number of subscribers for an event type."""
        with self._lock:
            return len(self._subscribers.get(event_type, {}))

    def clear(self) -> None:
        """Remove all subscribers."""
        with self._lock:
            self._subscribers.clear()