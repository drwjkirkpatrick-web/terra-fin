"""Tests for the CLI."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.cli import CLI, BANNER, HELP_TEXT
from core.engine import Engine
from core.config import MainConfig
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now


class MockSensor(SensorBase):
    name = "mock"
    metrics = ["value"]
    bus_type = "test"
    description = "mock"

    def _init_hardware(self):
        return False

    def _read_hardware(self):
        return None

    def _read_mock(self):
        return SensorReading(
            sensor_name="mock", timestamp=utc_now(),
            metrics={"value": 42.0}, units={"value": "u"},
        )


class MockHarvestModule:
    def __init__(self):
        self.entries = []

    def log_harvest(self, count, weight_kg, location, tree_id=None, notes=""):
        from core.types import HarvestEntry, utc_now
        entry = HarvestEntry(
            crop="test", timestamp=utc_now(),
            count=count, weight_kg=weight_kg, location=location,
            tree_id=tree_id, notes=notes,
        )
        self.entries.append(entry)
        return entry


class MockRecorder:
    def __init__(self):
        self._events = []

    def query_night_events(self):
        return self._events


class TestCLI:
    def _make_cli(self):
        sensors = {"mock": MockSensor(mock_mode=True)}
        engine = Engine(MainConfig(), sensors)
        harvest = MockHarvestModule()
        recorder = MockRecorder()
        cli = CLI(engine, recorder, {"greens": harvest})
        return cli, harvest, recorder

    def test_dispatch_soil(self, capsys):
        cli, _, _ = self._make_cli()
        cli._dispatch("soil")
        out = capsys.readouterr().out
        assert "not available" in out or "moisture" in out.lower()

    def test_dispatch_weather(self, capsys):
        cli, _, _ = self._make_cli()
        cli._dispatch("weather")
        out = capsys.readouterr().out
        assert "not available" in out or "temperature" in out.lower()

    def test_dispatch_help(self, capsys):
        cli, _, _ = self._make_cli()
        cli._dispatch("help")
        out = capsys.readouterr().out
        assert "Commands:" in out
        assert "soil" in out
        assert "quit" in out

    def test_dispatch_unknown(self, capsys):
        cli, _, _ = self._make_cli()
        cli._dispatch("unknown")
        out = capsys.readouterr().out
        assert "Unknown command" in out

    def test_dispatch_quit(self):
        cli, _, _ = self._make_cli()
        cli._dispatch("quit")
        assert cli._running is False

    def test_dispatch_harvest(self, capsys):
        cli, harvest, _ = self._make_cli()
        cli._dispatch("harvest kale 10 2.5")
        out = capsys.readouterr().out
        assert "Logged" in out
        assert len(harvest.entries) == 1

    def test_dispatch_harvest_unknown_crop(self, capsys):
        cli, _, _ = self._make_cli()
        cli._dispatch("harvest mango 10 2.5")
        out = capsys.readouterr().out
        assert "Unknown crop" in out

    def test_dispatch_night_no_events(self, capsys):
        cli, _, recorder = self._make_cli()
        cli._dispatch("night")
        out = capsys.readouterr().out
        assert "No night events" in out

    def test_dispatch_night_with_events(self, capsys):
        cli, _, recorder = self._make_cli()
        recorder._events = [
            {"event_type": "motion", "timestamp": "2026-01-01T00:00:00Z", "description": "test"}
        ]
        cli._dispatch("night")
        out = capsys.readouterr().out
        assert "1 night event" in out

    def test_dispatch_harvest_missing_args(self, capsys):
        cli, _, _ = self._make_cli()
        cli._dispatch("harvest")
        out = capsys.readouterr().out
        assert "Usage" in out