"""Tests for prompt handlers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.prompts import (
    handle_soil_status,
    handle_harvest_advice,
    handle_location,
    handle_weather,
    handle_day_night,
    handle_walk_summary,
    handle_night_report,
    handle_health,
)


# Fixtures
SOIL_SUMMARY = {
    "sensors": {
        "soil_moisture": {"metrics": {"soil_moisture_pct": 45.0}, "units": {}, "healthy": True},
        "soil_ph": {"metrics": {"soil_pH": 6.5}, "units": {}, "healthy": True},
    },
    "cross_sensor": {},
}

DRY_SUMMARY = {
    "sensors": {
        "soil_moisture": {"metrics": {"soil_moisture_pct": 15.0}, "units": {}, "healthy": True},
        "soil_ph": {"metrics": {"soil_pH": 5.0}, "units": {}, "healthy": True},
    },
    "cross_sensor": {},
}

WET_SUMMARY = {
    "sensors": {
        "soil_moisture": {"metrics": {"soil_moisture_pct": 85.0}, "units": {}, "healthy": True},
        "soil_ph": {"metrics": {"soil_pH": 8.0}, "units": {}, "healthy": True},
    },
    "cross_sensor": {},
}

NO_SOIL_SUMMARY = {"sensors": {}, "cross_sensor": {}}

LOCATION_SUMMARY = {
    "sensors": {},
    "cross_sensor": {"lat": -1.2864, "lon": 36.8222, "altitude_m": 1795.0, "fix_quality": "gps"},
}

WEATHER_SUMMARY = {
    "sensors": {
        "temp_humidity": {
            "metrics": {"temp_c": 25.0, "humidity_pct": 60.0}, "units": {}, "healthy": True,
        },
        "light": {
            "metrics": {"light_lux": 20000.0}, "units": {}, "healthy": True,
        },
    },
    "cross_sensor": {},
}

DAY_SUMMARY = {"sensors": {}, "cross_sensor": {"is_day": True}}
NIGHT_SUMMARY = {"sensors": {}, "cross_sensor": {"is_day": False}}

MOVING_SUMMARY = {
    "sensors": {},
    "cross_sensor": {"is_moving": True},
}
WALK_TRENDS = {"gps": {"distance_km": 2.5}}

HEALTH_SUMMARY = {
    "sensors": {
        "soil_moisture": {"metrics": {}, "units": {}, "healthy": True},
        "gps": {"metrics": {}, "units": {}, "healthy": False},
    },
    "cross_sensor": {},
}


class TestSoilStatus:
    def test_normal(self):
        result = handle_soil_status(SOIL_SUMMARY)
        assert "45.0" in result
        assert "moist" in result
        assert "6.5" in result
        assert "optimal" in result
        assert "awareness" in result

    def test_dry(self):
        result = handle_soil_status(DRY_SUMMARY)
        assert "dry" in result
        assert "acidic" in result

    def test_wet(self):
        result = handle_soil_status(WET_SUMMARY)
        assert "wet" in result
        assert "alkaline" in result

    def test_no_sensors(self):
        result = handle_soil_status(NO_SOIL_SUMMARY)
        assert "not available" in result


class TestHarvestAdvice:
    def test_optimal_avocado(self):
        result = handle_harvest_advice(SOIL_SUMMARY, "avocado")
        assert "optimal" in result.lower()

    def test_dry_avocado(self):
        result = handle_harvest_advice(DRY_SUMMARY, "avocado")
        assert "dry" in result

    def test_orange(self):
        result = handle_harvest_advice(SOIL_SUMMARY, "orange")
        # pH 6.5 is within orange range, moisture 45 within range
        assert "optimal" in result.lower()

    def test_greens(self):
        # moisture 45 is below greens minimum (50)
        result = handle_harvest_advice(SOIL_SUMMARY, "greens")
        assert "dry" in result

    def test_no_data(self):
        result = handle_harvest_advice(NO_SOIL_SUMMARY)
        assert "Insufficient" in result


class TestLocation:
    def test_with_gps(self):
        result = handle_location(LOCATION_SUMMARY)
        assert "-1.2864" in result
        assert "36.8222" in result
        assert "1795" in result
        assert "gps" in result

    def test_no_gps(self):
        result = handle_location(NO_SOIL_SUMMARY)
        assert "not available" in result


class TestWeather:
    def test_full_weather(self):
        result = handle_weather(WEATHER_SUMMARY)
        assert "25.0" in result
        assert "mild" in result
        assert "60%" in result
        assert "comfortable" in result
        assert "20000" in result
        assert "daylight" in result

    def test_no_weather(self):
        result = handle_weather(NO_SOIL_SUMMARY)
        assert "not available" in result


class TestDayNight:
    def test_day(self):
        result = handle_day_night(DAY_SUMMARY)
        assert "daytime" in result.lower()

    def test_night(self):
        result = handle_day_night(NIGHT_SUMMARY)
        assert "nighttime" in result.lower()

    def test_no_light(self):
        result = handle_day_night(NO_SOIL_SUMMARY)
        assert "not available" in result


class TestWalkSummary:
    def test_moving(self):
        result = handle_walk_summary(MOVING_SUMMARY, WALK_TRENDS)
        assert "moving" in result
        assert "2.50" in result

    def test_stationary(self):
        summary = {"cross_sensor": {"is_moving": False}}
        result = handle_walk_summary(summary, {})
        assert "stationary" in result


class TestNightReport:
    def test_no_events(self):
        result = handle_night_report([])
        assert "No night events" in result

    def test_with_events(self):
        events = [
            {"event_type": "motion", "description": "Movement detected", "timestamp": "2026-01-01T00:00:00Z"},
            {"event_type": "motion", "description": "Another movement", "timestamp": "2026-01-01T01:00:00Z"},
        ]
        result = handle_night_report(events)
        assert "2 night event" in result
        assert "motion" in result

    def test_many_events(self):
        events = [{"event_type": "x", "description": "d", "timestamp": "t"} for _ in range(10)]
        result = handle_night_report(events)
        assert "10 night event" in result
        assert "5 more" in result


class TestHealth:
    def test_healthy_and_unhealthy(self):
        result = handle_health(HEALTH_SUMMARY)
        assert "soil_moisture" in result
        assert "OK" in result
        assert "gps" in result
        assert "WARNING" in result

    def test_no_sensors(self):
        result = handle_health(NO_SOIL_SUMMARY)
        assert "No sensors" in result