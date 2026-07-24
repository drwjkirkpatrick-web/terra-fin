"""Tests for the AdaptationModule base class."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.adaptation_base import AdaptationModule, AdaptationResult
from core.types import SensorReading, utc_now


class TestModule(AdaptationModule):
    """Test module that returns a known result."""
    name = "test_module"
    category = "test"
    description = "test module"

    def analyze(self, reading, context):
        val = reading.metrics.get("value", 0.0) if reading else 0.0
        conf = context.get("confidence", 0.8)
        return AdaptationResult(
            module_name=self.name,
            category=self.category,
            timestamp=utc_now(),
            advisory=f"Value is {val}",
            confidence=conf,
            data={"value": val},
            severity="info" if val < 10 else "warning",
        )


class FailingModule(AdaptationModule):
    name = "failing"
    category = "test"
    description = "fails"

    def analyze(self, reading, context):
        raise RuntimeError("boom")


class TestAdaptationResult:
    def test_create(self):
        r = AdaptationResult("m", "cat", "ts", "advisory", 0.9, {"k": "v"})
        assert r.module_name == "m"
        assert r.confidence == 0.9
        assert r.severity == "info"

    def test_round_trip(self):
        r = AdaptationResult("m", "cat", "ts", "adv", 0.5, {"k": "v"}, "warning")
        d = r.to_dict()
        r2 = AdaptationResult.from_dict(d)
        assert r2.module_name == "m"
        assert r2.confidence == 0.5
        assert r2.severity == "warning"
        assert r2.data["k"] == "v"

    def test_repr(self):
        r = AdaptationResult("m", "cat", "ts", "adv", 0.8, {})
        assert "m" in repr(r)


class TestAdaptationModule:
    def test_process(self):
        m = TestModule()
        reading = SensorReading("s", utc_now(), {"value": 42.0}, {})
        result = m.process(reading, {"confidence": 0.9})
        assert result.module_name == "test_module"
        assert "42" in result.advisory
        assert result.confidence == 0.9

    def test_process_with_none_reading(self):
        m = TestModule()
        result = m.process(None, {})
        assert result.module_name == "test_module"
        assert "0" in result.advisory

    def test_process_exception_handled(self):
        m = FailingModule()
        result = m.process(None, {})
        assert "Analysis error" in result.advisory
        assert result.confidence == 0.0

    def test_history_accumulates(self):
        m = TestModule()
        for i in range(10):
            m.process(SensorReading("s", utc_now(), {"value": float(i)}, {}))
        assert len(m.get_history()) == 10

    def test_history_capped(self):
        m = TestModule()
        for i in range(600):
            m.process(SensorReading("s", utc_now(), {"value": float(i)}, {}))
        assert len(m.get_history()) == 500

    def test_get_advisory(self):
        m = TestModule()
        assert "No data yet" in m.get_advisory()
        m.process(SensorReading("s", utc_now(), {"value": 5.0}, {}))
        assert "5" in m.get_advisory()

    def test_health_check(self):
        m = TestModule()
        m.process(SensorReading("s", utc_now(), {"value": 1.0}, {}))
        hc = m.health_check()
        assert hc["name"] == "test_module"
        assert hc["category"] == "test"
        assert hc["enabled"] is True
        assert hc["history_count"] == 1
        assert hc["has_result"] is True

    def test_enable_disable(self):
        m = TestModule()
        assert m.enabled is True
        m.set_enabled(False)
        assert m.enabled is False
        result = m.process(None, {})
        assert "disabled" in result.advisory.lower()

    def test_thread_safety(self):
        import threading
        m = TestModule()
        errors = []

        def worker():
            try:
                for i in range(100):
                    m.process(SensorReading("s", utc_now(), {"value": float(i)}, {}))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        assert len(m.get_history()) == 400