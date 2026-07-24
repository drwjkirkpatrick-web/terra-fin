"""Deterministic prompt handlers for plain-English questions.

NOTE: These are pure functions that take sensor summary data and return
human-readable strings. No LLM, no hardware — fully testable in CI.

WHY: The Pi Zero 2 W cannot run an LLM. These handlers provide the same
user-facing guidance deterministically, using the sensor data available.
"""

from __future__ import annotations

from typing import Any


def handle_soil_status(summary: dict) -> str:
    """Report soil moisture and pH status.

    Non-alarmist: awareness tool, not a precision agricultural instrument.
    """
    sensors = summary.get("sensors", {})

    moisture = None
    pH = None

    sm = sensors.get("soil_moisture")
    if sm and "soil_moisture_pct" in sm.get("metrics", {}):
        moisture = sm["metrics"]["soil_moisture_pct"]

    ph = sensors.get("soil_ph")
    if ph and "soil_pH" in ph.get("metrics", {}):
        pH = ph["metrics"]["soil_pH"]

    parts = []
    if moisture is not None:
        cls = "dry" if moisture < 30 else ("moist" if moisture <= 70 else "wet")
        parts.append(f"Soil moisture is {moisture:.1f}%, classified as {cls}.")
    else:
        parts.append("Soil moisture sensor not available.")

    if pH is not None:
        cls = "acidic" if pH < 5.5 else ("optimal" if pH <= 7.5 else "alkaline")
        parts.append(f"pH is {pH:.1f}, classified as {cls}.")
    else:
        parts.append("pH sensor not available.")

    parts.append("This is an awareness tool — use a certified meter for precise measurements.")
    return " ".join(parts)


def handle_harvest_advice(summary: dict, crop: str = "avocado") -> str:
    """Give crop-specific harvest advice based on current soil conditions."""
    sensors = summary.get("sensors", {})

    moisture = None
    pH = None

    sm = sensors.get("soil_moisture")
    if sm and "soil_moisture_pct" in sm.get("metrics", {}):
        moisture = sm["metrics"]["soil_moisture_pct"]

    ph = sensors.get("soil_ph")
    if ph and "soil_pH" in ph.get("metrics", {}):
        pH = ph["metrics"]["soil_pH"]

    if moisture is None and pH is None:
        return "Insufficient sensor data for harvest advice."

    # Crop-specific thresholds
    thresholds = {
        "avocado": {"moisture": (30, 70), "pH": (5.5, 7.0)},
        "orange": {"moisture": (40, 70), "pH": (5.5, 6.5)},
        "greens": {"moisture": (50, 80), "pH": (6.0, 7.0)},
    }
    th = thresholds.get(crop, thresholds["avocado"])
    crop_name = crop if crop != "greens" else "greens"

    issues = []
    if moisture is not None:
        lo, hi = th["moisture"]
        if moisture < lo:
            issues.append(f"soil too dry for {crop_name}")
        elif moisture > hi:
            issues.append(f"soil too wet for {crop_name}")

    if pH is not None:
        lo, hi = th["pH"]
        if pH < lo or pH > hi:
            issues.append(f"pH outside {crop_name} range ({lo}-{hi})")

    if not issues:
        return f"Conditions look optimal for {crop_name} harvest."
    return "; ".join(issues) + ". Check with local agricultural extension for guidance."


def handle_location(summary: dict) -> str:
    """Report current GPS location."""
    cross = summary.get("cross_sensor", {})
    lat = cross.get("lat")
    lon = cross.get("lon")

    if lat is None or lon is None:
        return "GPS location not available."

    alt = cross.get("altitude_m")
    fix = cross.get("fix_quality", "unknown")

    parts = [f"You are at lat {lat:.4f}, lon {lon:.4f}."]
    if alt is not None:
        parts.append(f"Altitude {alt:.0f} meters.")
    parts.append(f"Fix quality: {fix}.")
    return " ".join(parts)


def handle_weather(summary: dict) -> str:
    """Report temperature, humidity, and light conditions."""
    sensors = summary.get("sensors", {})
    parts = []

    th = sensors.get("temp_humidity")
    if th:
        temp = th["metrics"].get("temp_c")
        hum = th["metrics"].get("humidity_pct")
        if temp is not None:
            cls = "cold" if temp < 15 else ("mild" if temp <= 28 else "hot")
            parts.append(f"Temperature {temp:.1f}°C ({cls}).")
        if hum is not None:
            cls = "dry" if hum < 40 else ("comfortable" if hum <= 70 else "humid")
            parts.append(f"Humidity {hum:.0f}% ({cls}).")
    else:
        parts.append("Temperature/humidity sensor not available.")

    light = sensors.get("light")
    if light:
        lux = light["metrics"].get("light_lux")
        if lux is not None:
            cls = _classify_light(lux)
            parts.append(f"Light level {lux:.0f} lux ({cls}).")
    else:
        parts.append("Light sensor not available.")

    return " ".join(parts) if parts else "Weather data not available."


def handle_day_night(summary: dict) -> str:
    """Report day/night status."""
    cross = summary.get("cross_sensor", {})
    is_day = cross.get("is_day")
    if is_day is None:
        return "Light sensor not available to determine day/night."
    if is_day:
        return "It is currently daytime. Day mode is active."
    return "It is currently nighttime. Night mode is active for monitoring."


def handle_walk_summary(summary: dict, trends: dict) -> str:
    """Summarize walking activity."""
    cross = summary.get("cross_sensor", {})
    is_moving = cross.get("is_moving", False)

    gps_trend = trends.get("gps", {})
    distance = gps_trend.get("distance_km", 0.0)

    parts = []
    if is_moving:
        parts.append("You are currently moving.")
    else:
        parts.append("You are currently stationary.")

    if distance > 0:
        parts.append(f"Distance covered: {distance:.2f} km.")

    return " ".join(parts)


def handle_night_report(events: list[dict]) -> str:
    """Summarize night mode events."""
    if not events:
        return "No night events recorded."

    parts = [f"{len(events)} night event(s) recorded:"]
    for ev in events[:5]:  # Show last 5
        ev_type = ev.get("event_type", "unknown")
        desc = ev.get("description", "")
        ts = ev.get("timestamp", "")
        parts.append(f"  [{ts}] {ev_type}: {desc}")

    if len(events) > 5:
        parts.append(f"  ... and {len(events) - 5} more.")

    return "\n".join(parts)


def handle_health(summary: dict) -> str:
    """Report sensor health summary."""
    sensors = summary.get("sensors", {})
    if not sensors:
        return "No sensors available."

    parts = ["Sensor health:"]
    for name, data in sensors.items():
        healthy = data.get("healthy", False)
        status = "OK" if healthy else "WARNING"
        parts.append(f"  {name}: {status}")

    return "\n".join(parts)


def _classify_light(lux: float) -> str:
    if lux < 10:
        return "night"
    elif lux < 500:
        return "dawn/dusk"
    elif lux < 10000:
        return "overcast"
    elif lux < 50000:
        return "daylight"
    else:
        return "bright"