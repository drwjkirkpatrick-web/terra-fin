"""Base class for adaptation modules (ESP32/MicroPython).

NOTE: All adaptation modules inherit from AdaptationModule. Uses _thread
locks. History kept in memory with a max-length cap.
"""

import logging
import time

try:
    import _thread as thread_mod
except ImportError:
    import threading as thread_mod

from .types import utc_now, AdaptationResult

logger = logging.getLogger(__name__)


def _make_lock():
    if hasattr(thread_mod, 'allocate_lock'):
        return thread_mod.allocate_lock()
    return thread_mod.Lock()


class AdaptationModule:
    """Abstract base class for all adaptation modules.

    Subclasses must set:
        name, category, description
    Subclasses must implement:
        analyze(reading, context) -> AdaptationResult
    """

    name = "base"
    category = "composite"
    description = "base adaptation module"

    def __init__(self):
        self._lock = _make_lock()
        self._history = []
        self._last_result = None
        self._enabled = True
        self._max_history = 200

    def process(self, reading=None, context=None):
        if not self._enabled:
            return AdaptationResult(
                module_name=self.name, category=self.category,
                timestamp=utc_now(), advisory="Module disabled",
                confidence=0.0, data={},
            )
        ctx = context or {}
        try:
            result = self.analyze(reading, ctx)
            with self._lock:
                self._last_result = result
                self._history.append(result.to_dict())
                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history:]
            return result
        except Exception as e:
            logger.error("[%s] analyze failed: %s", self.name, e)
            return AdaptationResult(
                module_name=self.name, category=self.category,
                timestamp=utc_now(), advisory="Analysis error: {}".format(e),
                confidence=0.0, data={},
            )

    def analyze(self, reading, context):
        raise NotImplementedError

    def get_history(self):
        with self._lock:
            return list(self._history)

    def get_advisory(self):
        with self._lock:
            if self._last_result:
                return self._last_result.advisory
            return "No advisory yet."

    def get_last_result(self):
        with self._lock:
            return self._last_result

    def health_check(self):
        with self._lock:
            return {
                "name": self.name, "category": self.category,
                "enabled": self._enabled,
                "history_count": len(self._history),
                "last_advisory": self.get_advisory(),
            }

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def _result(self, advisory, confidence, severity="info", **kwargs):
        return AdaptationResult(
            module_name=self.name, category=self.category,
            timestamp=utc_now(), advisory=advisory,
            confidence=confidence, data=kwargs, severity=severity,
        )
