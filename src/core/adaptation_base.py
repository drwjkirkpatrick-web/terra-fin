"""Base class for adaptation modules.

NOTE: All 30 adaptation modules inherit from AdaptationModule. This provides
a consistent interface for recording observations, generating advisories,
tracking trends, and recommending actions based on changing conditions.

WHY: A single base class ensures all adaptation modules can be managed
identically by the orchestrator, CLI, and dashboard — regardless of whether
they track weather, soil, or animal/insect changes.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from .types import SensorReading, utc_now

logger = logging.getLogger(__name__)


class AdaptationModule(ABC):
    """Abstract base class for all adaptation modules.

    Subclasses must set these class attributes:
        name: str         — module identifier (e.g. "rain_predictor")
        category: str     — "weather", "soil", "animal", "insect", "composite"
        description: str   — human-readable description

    Subclasses must implement:
        analyze(reading: SensorReading | None, context: dict) -> AdaptationResult

    Subclasses may override:
        record(reading: SensorReading | None, context: dict) -> None
        get_history() -> list[dict]
        get_advisory() -> str
        health_check() -> dict
    """

    name: str = "base"
    category: str = "composite"
    description: str = "base adaptation module"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._history: list[dict] = []
        self._last_result: "AdaptationResult | None" = None
        self._enabled = True

    def process(self, reading: SensorReading | None = None, context: dict | None = None) -> "AdaptationResult":
        """Process a reading and context, return an AdaptationResult.

        This is the main entry point called by the orchestrator on each poll.
        It calls analyze() and records the result.
        """
        if not self._enabled:
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory="Module disabled",
                confidence=0.0,
                data={},
            )

        ctx = context or {}
        try:
            result = self.analyze(reading, ctx)
            with self._lock:
                self._last_result = result
                self._history.append(result.to_dict())
                if len(self._history) > 500:
                    self._history = self._history[-500:]
            return result
        except Exception as e:
            logger.error("[%s] analyze failed: %s", self.name, e)
            return AdaptationResult(
                module_name=self.name,
                category=self.category,
                timestamp=utc_now(),
                advisory=f"Analysis error: {e}",
                confidence=0.0,
                data={},
            )

    @abstractmethod
    def analyze(self, reading: SensorReading | None, context: dict) -> "AdaptationResult":
        """Analyze a sensor reading within context. Return an AdaptationResult."""
        ...

    def get_history(self) -> list[dict]:
        """Return history of past results."""
        with self._lock:
            return list(self._history)

    def get_advisory(self) -> str:
        """Return the most recent advisory text."""
        with self._lock:
            if self._last_result is None:
                return f"No data yet from {self.name}"
            return self._last_result.advisory

    def health_check(self) -> dict:
        """Return health/status info."""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "enabled": self._enabled,
            "history_count": len(self._history),
            "has_result": self._last_result is not None,
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled


class AdaptationResult:
    """Result from an adaptation module analysis.

    NOTE: This is a plain class (not a dataclass) to keep it lightweight
    and avoid from_dict/to_dict pitfalls with computed properties.
    """

    def __init__(
        self,
        module_name: str,
        category: str,
        timestamp: str,
        advisory: str,
        confidence: float,
        data: dict[str, Any],
        severity: str = "info",
    ) -> None:
        self.module_name = module_name
        self.category = category
        self.timestamp = timestamp
        self.advisory = advisory
        self.confidence = confidence  # 0.0 to 1.0
        self.data = data
        self.severity = severity  # "info", "advisory", "warning", "critical"

    def to_dict(self) -> dict:
        return {
            "module_name": self.module_name,
            "category": self.category,
            "timestamp": self.timestamp,
            "advisory": self.advisory,
            "confidence": self.confidence,
            "data": self.data,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AdaptationResult":
        return cls(
            module_name=data["module_name"],
            category=data["category"],
            timestamp=data["timestamp"],
            advisory=data["advisory"],
            confidence=data["confidence"],
            data=data.get("data", {}),
            severity=data.get("severity", "info"),
        )

    def __repr__(self) -> str:
        return f"AdaptationResult({self.module_name}, conf={self.confidence:.0%}, sev={self.severity})"