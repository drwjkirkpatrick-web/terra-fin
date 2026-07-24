"""Core type definitions for the Agricultural Walking Stick Agent.

NOTE: These dataclasses are the shared contract across all modules — sensors,
harvest modules, recorder, prompts, and night mode all use these types.
A single author wrote this file to ensure consistency.

WHY: Centralizing types prevents API drift between subagent-built modules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DeviceMode(Enum):
    """Operating mode for the walking stick agent."""
    DAY = "day"
    NIGHT = "night"
    STANDBY = "standby"


# ---------------------------------------------------------------------------
# Sensor Reading
# ---------------------------------------------------------------------------

@dataclass
class SensorReading:
    """A single reading from any sensor.

    NOTE: metrics must be dict[str, float] to maintain a consistent contract
    across all sensors. String-valued data goes in metadata.
    """
    sensor_name: str
    timestamp: str  # ISO 8601 UTC
    metrics: dict[str, float]
    units: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SensorReading":
        valid = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# GPS Position
# ---------------------------------------------------------------------------

@dataclass
class GPSPosition:
    """A GPS fix with latitude, longitude, and optional altitude."""
    lat: float
    lon: float
    altitude_m: float | None = None
    timestamp: str = ""
    fix_quality: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GPSPosition":
        valid = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Harvest Entry
# ---------------------------------------------------------------------------

@dataclass
class HarvestEntry:
    """A single harvest log entry."""
    crop: str
    timestamp: str
    count: int
    weight_kg: float
    location: str
    notes: str = ""
    tree_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "HarvestEntry":
        valid = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Night Event
# ---------------------------------------------------------------------------

@dataclass
class NightEvent:
    """An event detected during night mode sentinel operation."""
    event_type: str
    timestamp: str
    description: str
    location: GPSPosition | None = None
    severity: str = "info"

    def to_dict(self) -> dict:
        d = asdict(self) if self.location is not None else {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "description": self.description,
            "location": None,
            "severity": self.severity,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "NightEvent":
        valid = {f.name for f in fields(cls)}
        loc_data = data.get("location")
        location = GPSPosition.from_dict(loc_data) if isinstance(loc_data, dict) else loc_data
        filtered = {k: v for k, v in data.items() if k in valid and k != "location"}
        return cls(location=location, **filtered)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_now() -> str:
    """Return current time as ISO 8601 UTC string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp into a datetime object."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))