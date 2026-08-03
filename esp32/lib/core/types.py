"""Core type definitions for Terra-Fin Agent (ESP32/MicroPython).

NOTE: Uses JSON for serialization. Compatible with MicroPython v1.23+.
Dataclasses available via micropython-dataclasses package or built-in.
"""

import json
import time

try:
    from dataclasses import dataclass, field, asdict, fields
    _HAS_DATACLASSES = True
except Exception:
    _HAS_DATACLASSES = False


class DeviceMode:
    DAY = "day"
    NIGHT = "night"
    STANDBY = "standby"


class _SimpleDataClass:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__dict__ if not k.startswith('_')}

    @classmethod
    def from_dict(cls, data):
        valid = set(getattr(cls, '_fields', [])) or set(data.keys())
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


def utc_now():
    t = time.gmtime(time.time())
    return '{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z'.format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )


if _HAS_DATACLASSES:
    @dataclass
    class SensorReading:
        sensor_name: str
        timestamp: str
        metrics: dict
        units: dict
        metadata: dict = field(default_factory=dict)

        def to_dict(self):
            return asdict(self)

        @classmethod
        def from_dict(cls, data):
            valid = {f.name for f in fields(cls)}
            filtered = {k: v for k, v in data.items() if k in valid}
            return cls(**filtered)
else:
    class SensorReading(_SimpleDataClass):
        _fields = ['sensor_name', 'timestamp', 'metrics', 'units', 'metadata']
        def __init__(self, sensor_name='', timestamp='', metrics=None, units=None, metadata=None):
            self.sensor_name = sensor_name
            self.timestamp = timestamp
            self.metrics = metrics if metrics is not None else {}
            self.units = units if units is not None else {}
            self.metadata = metadata if metadata is not None else {}


if _HAS_DATACLASSES:
    @dataclass
    class GPSPosition:
        lat: float
        lon: float
        altitude_m: float = None
        timestamp: str = ''
        fix_quality: str = 'unknown'

        def to_dict(self):
            return asdict(self)

        @classmethod
        def from_dict(cls, data):
            valid = {f.name for f in fields(cls)}
            filtered = {k: v for k, v in data.items() if k in valid}
            return cls(**filtered)
else:
    class GPSPosition(_SimpleDataClass):
        _fields = ['lat', 'lon', 'altitude_m', 'timestamp', 'fix_quality']
        def __init__(self, lat=0.0, lon=0.0, altitude_m=None, timestamp='', fix_quality='unknown'):
            self.lat = lat
            self.lon = lon
            self.altitude_m = altitude_m
            self.timestamp = timestamp
            self.fix_quality = fix_quality


if _HAS_DATACLASSES:
    @dataclass
    class HarvestEntry:
        crop: str
        timestamp: str
        count: int
        weight_kg: float
        location: str
        notes: str = ''
        tree_id: str = None

        def to_dict(self):
            return asdict(self)

        @classmethod
        def from_dict(cls, data):
            valid = {f.name for f in fields(cls)}
            filtered = {k: v for k, v in data.items() if k in valid}
            return cls(**filtered)
else:
    class HarvestEntry(_SimpleDataClass):
        _fields = ['crop', 'timestamp', 'count', 'weight_kg', 'location', 'notes', 'tree_id']
        def __init__(self, crop='', timestamp='', count=0, weight_kg=0.0, location='', notes='', tree_id=None):
            self.crop = crop
            self.timestamp = timestamp
            self.count = count
            self.weight_kg = weight_kg
            self.location = location
            self.notes = notes
            self.tree_id = tree_id


if _HAS_DATACLASSES:
    @dataclass
    class NightEvent:
        event_type: str
        timestamp: str
        description: str
        location: dict = field(default_factory=dict)
        severity: str = 'info'

        def to_dict(self):
            return asdict(self)

        @classmethod
        def from_dict(cls, data):
            valid = {f.name for f in fields(cls)}
            filtered = {k: v for k, v in data.items() if k in valid}
            return cls(**filtered)
else:
    class NightEvent(_SimpleDataClass):
        _fields = ['event_type', 'timestamp', 'description', 'location', 'severity']
        def __init__(self, event_type='', timestamp='', description='', location=None, severity='info'):
            self.event_type = event_type
            self.timestamp = timestamp
            self.description = description
            self.location = location if location is not None else {}
            self.severity = severity


if _HAS_DATACLASSES:
    @dataclass
    class AdaptationResult:
        module_name: str
        category: str
        timestamp: str
        advisory: str
        confidence: float
        data: dict = field(default_factory=dict)
        severity: str = 'info'

        def to_dict(self):
            return asdict(self)

        @classmethod
        def from_dict(cls, data):
            valid = {f.name for f in fields(cls)}
            filtered = {k: v for k, v in data.items() if k in valid}
            return cls(**filtered)
else:
    class AdaptationResult(_SimpleDataClass):
        _fields = ['module_name', 'category', 'timestamp', 'advisory', 'confidence', 'data', 'severity']
        def __init__(self, module_name='', category='', timestamp='', advisory='', confidence=0.0, data=None, severity='info'):
            self.module_name = module_name
            self.category = category
            self.timestamp = timestamp
            self.advisory = advisory
            self.confidence = confidence
            self.data = data if data is not None else {}
            self.severity = severity
