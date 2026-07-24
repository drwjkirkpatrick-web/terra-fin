"""Tests for the RainPredictor adaptation module.

NOTE: These tests exercise every decision branch in RainPredictor.analyze —
high humidity with a dropping temperature (rain likely), high humidity with a
stable temperature (rain possible), low humidity (dry), no reading (no data),
the disabled-module path via process(), the data-dict contract, and the
process()/history integration. All tests use mock SensorReadings and a trends
context dict mirroring the shape produced by Engine.get_trends().

WHY: Rain advisories directly affect harvest operations — covering bins,
delaying picking, moving produce indoors. Each branch must produce the exact
advisory text, confidence, and severity the spec requires so downstream
consumers (CLI, dashboard, prompts) can trust the result without re-checking.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.adaptation_base import AdaptationResult
from core.types import SensorReading, utc_now
from adaptation.rain_predictor import RainPredictor


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _reading(temp_c: float, humidity_pct: float) -> SensorReading:
    """Build a temp_humidity SensorReading with the given metrics."""
    return SensorReading(
        sensor_name="temp_humidity",
        timestamp=utc_now(),
        metrics={"temp_c": temp_c, "humidity_pct": humidity_pct},
        units={"temp_c": "°C", "humidity_pct": "%"},
    )


def _trends(temp_c_delta: float) -> dict:
    """Build a context dict with trends mirroring Engine.get_trends() shape.

    The engine keys trends by sensor name; each value is a dict with
    ``{metric}_delta`` entries.
    """
    return {
        "trends": {
            "temp_humidity": {
                "count": 5,
                "first_timestamp": utc_now(),
                "last_timestamp": utc_now(),
                "temp_c_delta": temp_c_delta,
                "temp_c_rate": round(temp_c_delta / 5, 4),
                "humidity_pct_delta": 5.0,
                "humidity_pct_rate": 1.0,
            }
        }
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

class TestRainPredictorAttributes:
    def test_class_attributes(self):
        """Class attributes must match the AdaptationModule contract."""
        assert RainPredictor.name == "rain_predictor"
        assert RainPredictor.category == "weather"
        assert "rain likelihood" in RainPredictor.description.lower()


class TestRainPredictorAnalysis:
    def test_high_humidity_dropping_temp_rain_likely(self):
        """Humidity > 80 % and temp dropping → rain likely, conf 0.8, advisory."""
        m = RainPredictor()
        reading = _reading(temp_c=20.0, humidity_pct=85.0)
        result = m.analyze(reading, _trends(temp_c_delta=-1.5))

        assert result.advisory == "Rain likely within hours. Consider covering harvest bins."
        assert result.confidence == 0.8
        assert result.severity == "advisory"
        assert result.data["prediction"] == "rain_likely"
        assert result.data["humidity"] == 85.0
        assert result.data["trend"] == "dropping"

    def test_high_humidity_stable_temp_rain_possible(self):
        """Humidity > 70 % and temp stable → rain possible, conf 0.6, info."""
        m = RainPredictor()
        reading = _reading(temp_c=22.0, humidity_pct=75.0)
        result = m.analyze(reading, _trends(temp_c_delta=0.0))

        assert result.advisory == "Humidity rising — rain possible. Monitor sky conditions."
        assert result.confidence == 0.6
        assert result.severity == "info"
        assert result.data["prediction"] == "rain_possible"
        assert result.data["trend"] == "stable"

    def test_low_humidity_dry_conditions(self):
        """Humidity < 50 % → dry, no rain expected, conf 0.7."""
        m = RainPredictor()
        reading = _reading(temp_c=28.0, humidity_pct=35.0)
        result = m.analyze(reading, _trends(temp_c_delta=0.5))

        assert result.advisory == "Dry conditions — no rain expected."
        assert result.confidence == 0.7
        assert result.severity == "info"
        assert result.data["prediction"] == "dry"
        assert result.data["humidity"] == 35.0

    def test_no_reading_no_data(self):
        """No reading at all → no-data advisory, confidence 0.0."""
        m = RainPredictor()
        result = m.analyze(None, {})

        assert result.advisory == "No humidity data available for rain prediction."
        assert result.confidence == 0.0
        assert result.severity == "info"
        assert result.data["prediction"] == "no_data"
        assert result.data["humidity"] is None
        assert result.data["temp"] is None

    def test_reading_without_humidity_metric(self):
        """Reading present but missing humidity_pct → no-data advisory."""
        m = RainPredictor()
        reading = SensorReading(
            sensor_name="temp_humidity",
            timestamp=utc_now(),
            metrics={"temp_c": 21.0},  # no humidity_pct
            units={"temp_c": "°C"},
        )
        result = m.analyze(reading, {})

        assert result.confidence == 0.0
        assert result.data["prediction"] == "no_data"
        assert result.data["humidity"] is None

    def test_high_humidity_rising_temp_not_rain_likely(self):
        """Humidity > 80 % but temp rising → should NOT trigger rain_likely.

        With a rising trend the first branch (dropping) is skipped; since
        trend != "stable" the second branch is also skipped, so we fall
        through to the stable/ambiguous advisory.
        """
        m = RainPredictor()
        reading = _reading(temp_c=25.0, humidity_pct=82.0)
        result = m.analyze(reading, _trends(temp_c_delta=0.8))

        assert result.data["prediction"] != "rain_likely"
        assert result.data["trend"] == "rising"
        assert result.confidence == 0.3


class TestRainPredictorProcessAndData:
    def test_disabled_module(self):
        """A disabled module returns a 'Module disabled' advisory via process()."""
        m = RainPredictor()
        m.set_enabled(False)
        result = m.process(None, {})

        assert "disabled" in result.advisory.lower()
        assert result.confidence == 0.0

    def test_data_dict_contract(self):
        """The data dict must always contain humidity, temp, trend, prediction."""
        m = RainPredictor()
        reading = _reading(temp_c=19.0, humidity_pct=88.0)
        result = m.analyze(reading, _trends(temp_c_delta=-2.0))

        assert "humidity" in result.data
        assert "temp" in result.data
        assert "trend" in result.data
        assert "prediction" in result.data
        assert result.data["temp"] == 19.0

    def test_process_records_history(self):
        """process() should record results in history and update advisory."""
        m = RainPredictor()
        reading = _reading(temp_c=18.0, humidity_pct=45.0)
        m.process(reading, _trends(temp_c_delta=0.0))

        assert len(m.get_history()) == 1
        assert "rain" in m.get_advisory().lower() or "dry" in m.get_advisory().lower()