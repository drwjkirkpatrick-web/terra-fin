"""Deterministic prompt handlers for plain-English questions (ESP32/MicroPython).

NOTE: These are pure functions that take sensor summary data and return
human-readable strings. No LLM, no hardware.
"""


def handle_soil_status(summary):
    """Report soil moisture and pH status."""
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
        parts.append("Soil moisture is {:.1f}%, classified as {}.".format(moisture, cls))
    else:
        parts.append("Soil moisture sensor not available.")
    if pH is not None:
        cls = "acidic" if pH < 5.5 else ("optimal" if pH <= 7.5 else "alkaline")
        parts.append("pH is {:.1f}, classified as {}.".format(pH, cls))
    else:
        parts.append("pH sensor not available.")
    parts.append("This is an awareness tool -- use a certified meter for precise measurements.")
    return " ".join(parts)


def handle_harvest_advice(summary, crop="avocado"):
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
    thresholds = {
        "avocado": {"moisture": (30, 70), "pH": (5.5, 7.0)},
        "orange": {"moisture": (40, 70), "pH": (5.5, 6.5)},
        "greens": {"moisture": (50, 80), "pH": (6.0, 7.0)},
    }
    t = thresholds.get(crop, thresholds["avocado"])
    parts = []
    parts.append("Harvest advice for {}:".format(crop))
    if moisture is not None:
        m_min, m_max = t["moisture"]
        if moisture < m_min:
            parts.append("Soil is too dry ({:.1f}%). Consider irrigating before harvest.".format(moisture))
        elif moisture > m_max:
            parts.append("Soil is wet ({:.1f}%). Wait for drainage to avoid root damage.".format(moisture))
        else:
            parts.append("Soil moisture is good ({:.1f}%).".format(moisture))
    if pH is not None:
        p_min, p_max = t["pH"]
        if pH < p_min:
            parts.append("Soil is too acidic ({:.1f}). Consider lime amendment.".format(pH))
        elif pH > p_max:
            parts.append("Soil is too alkaline ({:.1f}). Consider sulfur amendment.".format(pH))
        else:
            parts.append("pH is in optimal range ({:.1f}).".format(pH))
    return " ".join(parts)


def handle_location(summary):
    """Report GPS location."""
    cross = summary.get("cross_sensor", {})
    lat = cross.get("lat")
    lon = cross.get("lon")
    if lat is not None and lon is not None:
        return "Location: {:.6f}, {:.6f}".format(lat, lon)
    return "GPS not available."


def handle_weather(summary):
    """Report weather conditions."""
    sensors = summary.get("sensors", {})
    temp = None
    humidity = None
    light = None
    th = sensors.get("temp_humidity")
    if th and "temp_c" in th.get("metrics", {}):
        temp = th["metrics"]["temp_c"]
    if th and "humidity_pct" in th.get("metrics", {}):
        humidity = th["metrics"]["humidity_pct"]
    ls = sensors.get("light")
    if ls and "light_lux" in ls.get("metrics", {}):
        light = ls["metrics"]["light_lux"]
    parts = []
    if temp is not None:
        parts.append("Temperature: {:.1f} C".format(temp))
    if humidity is not None:
        parts.append("Humidity: {:.1f}%".format(humidity))
    if light is not None:
        parts.append("Light: {:.1f} lux".format(light))
    if not parts:
        return "Weather sensors not available."
    return " | ".join(parts)


def handle_day_night(summary):
    """Report day/night status."""
    cross = summary.get("cross_sensor", {})
    is_day = cross.get("is_day", False)
    return "It is {}.".format("daytime" if is_day else "nighttime")


def handle_walk_summary(summary):
    """Report walking summary from IMU."""
    cross = summary.get("cross_sensor", {})
    is_moving = cross.get("is_moving", False)
    accel = cross.get("accel_magnitude", 0.0)
    if is_moving:
        return "Walking detected. Acceleration magnitude: {:.2f} g".format(accel)
    return "Stationary. Acceleration magnitude: {:.2f} g".format(accel)


def handle_health(summary):
    """Report sensor health."""
    sensors = summary.get("sensors", {})
    parts = []
    for name, data in sensors.items():
        healthy = data.get("healthy", False)
        parts.append("{}: {}".format(name, "OK" if healthy else "ERROR"))
    if not parts:
        return "No sensor health data."
    return " | ".join(parts)
