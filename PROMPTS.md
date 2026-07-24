# Build Prompts: Agricultural Walking Stick Agent

> **Platform:** Raspberry Pi Zero 2 W on a walking stick
> **Sensors:** Ground moisture probe (tip), pH probe (tip), GPS (location),
> ambient temp/humidity (air), ambient light (day/night), IMU (motion/orientation)
> **Harvest modules:** Avocado, Orange, Local Greens
> **Modes:** Day mode (walking companion), Night mode (stationary sentinel)
> **Mock-safe:** All sensors run in mock mode for hardware-free development

---

## Build-Order Table

| # | Module | File | Depends On | Owner |
|---|--------|------|------------|-------|
| 0.1 | Core Types | `src/core/types.py` | — | Parent |
| 0.2 | Config | `src/core/config.py` | types | Parent |
| 0.3 | Sensor Base | `src/core/sensor_base.py` | types | Parent |
| 0.4 | Mock Manager | `src/core/mock_manager.py` | — | Parent |
| 0.5 | Event Bus | `src/core/event_bus.py` | types | Parent |
| 1.1 | Soil Moisture Sensor | `src/sensors/soil_moisture.py` | sensor_base, mock_manager | Subagent A |
| 1.2 | Soil pH Sensor | `src/sensors/soil_ph.py` | sensor_base, mock_manager | Subagent B |
| 1.3 | GPS Module | `src/sensors/gps.py` | sensor_base, mock_manager | Subagent C |
| 1.4 | Temp/Humidity Sensor | `src/sensors/temp_humidity.py` | sensor_base, mock_manager | Subagent D |
| 1.5 | Light Sensor | `src/sensors/light_sensor.py` | sensor_base, mock_manager | Subagent E |
| 1.6 | IMU Sensor | `src/sensors/imu.py` | sensor_base, mock_manager | Subagent F |
| 2.1 | Avocado Harvest Module | `src/modules/avocado.py` | types, config | Subagent G |
| 2.2 | Orange Harvest Module | `src/modules/orange.py` | types, config | Subagent H |
| 2.3 | Local Greens Module | `src/modules/greens.py` | types, config | Subagent I |
| 3.1 | Engine | `src/core/engine.py` | types, config, sensors | Parent |
| 3.2 | Recorder | `src/core/recorder.py` | types, config | Parent |
| 4.1 | Prompts (Question Handlers) | `src/core/prompts.py` | engine, types | Parent |
| 4.2 | Night Mode Sentinel | `src/modules/night_mode.py` | engine, event_bus, sensors | Parent |
| 5.1 | Dashboard | `src/core/dashboard.py` | engine, recorder | Parent |
| 5.2 | CLI | `src/core/cli.py` | engine, prompts | Parent |
| 6.1 | Main Orchestrator | `src/main.py` | all core modules | Parent |
| 6.2 | Hardware Docs | `hardware/*.md` | — | Parent |
| 7.1 | Full Test Suite | `tests/` | all modules | Parent |

---

## Phase 0: Foundation (Parent builds directly)

### Prompt 0.1 — Core Types

Create `src/core/types.py` with:

- `SensorReading` dataclass: `sensor_name: str`, `timestamp: str` (ISO 8601 UTC),
  `metrics: dict[str, float]`, `units: dict[str, str]`, `metadata: dict[str, Any]`
- `HarvestEntry` dataclass: `crop: str`, `timestamp: str`, `count: int`,
  `weight_kg: float`, `location: str`, `notes: str`, `tree_id: str | None`
- `GPSPosition` dataclass: `lat: float`, `lon: float`, `altitude_m: float | None`,
  `timestamp: str`, `fix_quality: str`
- `NightEvent` dataclass: `event_type: str`, `timestamp: str`, `description: str`,
  `location: GPSPosition | None`, `severity: str`
- `DeviceMode` enum: `DAY`, `NIGHT`, `STANDBY`
- `to_dict()` and `from_dict()` on all dataclasses (filter computed properties in from_dict)
- `__init__.py` exports all types

Tests: `tests/test_types.py` — verify round-trip serialization, enum values,
missing-field handling in from_dict.

### Prompt 0.2 — Config

Create `src/core/config.py` with:

- `SensorConfig` dataclass: `enabled: bool = True`, `poll_interval_s: float = 5.0`,
  `mock_mode: bool = True`
- `GPSConfig`: adds `port: str = "/dev/ttyACM0"`, `baud: int = 9600`
- `SoilConfig`: adds `adc_channel: int = 0`, `dry_threshold: float = 30.0`,
  `wet_threshold: float = 70.0`, `probe_depth_cm: float = 15.0`
- `pHConfig`: adds `adc_channel: int = 1`, `min_pH: float = 3.0`, `max_pH: float = 10.0`
- `TempHumidityConfig`: adds `i2c_address: int = 0x48` (SHT40 default)
- `LightConfig`: adds `adc_channel: int = 2`, `night_lux_threshold: float = 10.0`
- `IMUConfig`: adds `i2c_address: int = 0x68` (MPU-6050)
- `NightModeConfig`: `enabled: bool = True`, `poll_interval_s: float = 30.0`,
  `motion_alert_threshold: float = 0.5`, `log_only: bool = True`
- `DashboardConfig`: `port: int = 9195`, `host: str = "0.0.0.0"`
- `MainConfig`: composes all sub-configs + `device_name: str = "agri-stick-01"`,
  `mode: str = "day"`, `storage_path: str = "data/agri_stick.db"`
- `from_yaml(path)` classmethod that reads a YAML file and constructs MainConfig
- `from_env()` classmethod that reads from environment variables with `AGRI_` prefix

Tests: `tests/test_config.py` — verify defaults, YAML loading, env loading,
sub-config access, immutability.

### Prompt 0.3 — Sensor Base

Create `src/core/sensor_base.py` with:

- `SensorBase` abstract class matching the SensorBase GPIO/ADC pattern from
  `edge-deployment-workflows` skill:
  - Class attributes: `name: str`, `metrics: list[str]`, `bus_type: str`,
    `description: str`
  - `initialize()` → bool (calls `_init_hardware()`, sets `self._initialized`)
  - `read()` → `SensorReading | None` (wraps `_read_hardware()` or `_read_mock()`)
  - `_init_hardware()` → bool (abstract)
  - `_read_hardware()` → `SensorReading | None` (abstract)
  - `_read_mock()` → `SensorReading` (returns zeros by default, override for realism)
  - `health_check()` → dict (name, bus_type, metrics, initialized, healthy, mock_mode)
  - `cleanup()` → None (override for GPIO cleanup etc.)
  - `is_healthy` property
- All hardware imports wrapped in `try/except ImportError` with `None` fallback

Tests: `tests/test_sensor_base.py` — test mock fallback when hardware unavailable,
health_check shape, read() error wrapping, cleanup calls.

### Prompt 0.4 — Mock Manager

Create `src/core/mock_manager.py` with:

- `MockManager` class that generates realistic time-varying sensor data:
  - `get(metric_name, jitter=0.05)` → float: random walk around a per-metric
    baseline with optional jitter fraction
  - Per-metric baselines: soil_moisture_pct=45.0, soil_pH=6.5, gps_lat=-1.2864,
    gps_lon=36.8222, temp_c=24.0, humidity_pct=60.0, light_lux=15000.0,
    accel_x=0.0, accel_y=0.0, accel_z=9.81
  - `set_baseline(metric, value)` to override
  - `reset()` to return all baselines to defaults
  - Diurnal cycle for temp/humidity/light (sine wave on time of day)
  - Thread-safe (threading.Lock)

Tests: `tests/test_mock_manager.py` — verify get returns float in range,
jitter stays within bounds, diurnal cycle varies by time, set_baseline works,
reset restores defaults, thread safety (concurrent get calls).

### Prompt 0.5 — Event Bus

Create `src/core/event_bus.py` with:

- `EventBus` class: lightweight async-free pub/sub using threading
  - `subscribe(event_type: str, callback: Callable)` → subscription ID
  - `unsubscribe(sub_id: str)` → bool
  - `publish(event_type: str, data: dict)` → int (number of subscribers notified)
  - Thread-safe with `threading.RLock`
  - `event_types` class attribute listing known event types:
    SENSOR_READING, NIGHT_ALERT, HARVEST_LOGGED, MODE_CHANGE, GPS_FIX, LOW_BATTERY
  - No asyncio dependency (threading-based for Pi Zero simplicity)

Tests: `tests/test_event_bus.py` — subscribe+publish, unsubscribe, multiple
subscribers, thread safety, unknown event type, callback exception isolation.

---

## Phase 1: Sensor Modules (Each delegated to 1 subagent)

### Prompt 1.1 — Soil Moisture Sensor

Create `src/sensors/soil_moisture.py` and `tests/test_soil_moisture.py`.

- `SoilMoistureSensor(SensorBase)` class:
  - `name = "soil_moisture"`, `metrics = ["soil_moisture_pct"]`,
    `bus_type = "adc"`, `description = "Capacitive soil moisture probe at stick tip"`
  - Constructor: `(config: SoilConfig | None = None, mock_mode: bool = False)`
  - `_init_hardware()`: try import `adafruit_mcp3xxx`, set up ADC channel,
    return False if unavailable
  - `_read_hardware()`: read ADC voltage, apply calibration curve
    (voltage → moisture %), return SensorReading
  - `_read_mock()`: use MockManager for soil_moisture_pct
  - Calibration curve: 0V = 0% (dry), 3.3V = 100% (wet), linear
  - `classify(value) -> str`: "dry" (<30%), "moist" (30-70%), "wet" (>70%)
  - `cleanup()`: release ADC channel if hardware initialized

Tests: mock mode read returns valid reading, classify thresholds, health_check
shape, cleanup no-op in mock, read twice consistency, py_compile.

### Prompt 1.2 — Soil pH Sensor

Create `src/sensors/soil_ph.py` and `tests/test_soil_ph.py`.

- `SoilPHSensor(SensorBase)` class:
  - `name = "soil_ph"`, `metrics = ["soil_pH"]`, `bus_type = "adc"`
  - Constructor: `(config: pHConfig | None = None, mock_mode: bool = False)`
  - `_init_hardware()`: try import ADC library, set up channel 1
  - `_read_hardware()`: read ADC, convert voltage to pH via calibration
    (pH 0 = 0V, pH 14 = 3.3V, linear)
  - `_read_mock()`: use MockManager, clamp to [3.0, 10.0]
  - `classify(value) -> str`: "acidic" (<5.5), "optimal" (5.5-7.5), "alkaline" (>7.5)
  - `cleanup()`

Tests: mock read, classify thresholds, health_check, cleanup, read twice.

### Prompt 1.3 — GPS Module

Create `src/sensors/gps.py` and `tests/test_gps.py`.

- `GPSSensor(SensorBase)` class:
  - `name = "gps"`, `metrics = ["lat", "lon", "altitude_m"]`,
    `bus_type = "serial"`
  - Constructor: `(config: GPSConfig | None = None, mock_mode: bool = False)`
  - `_init_hardware()`: try import `serial`, open `/dev/ttyACM0` at 9600 baud,
    return False if serial unavailable
  - `_read_hardware()`: read NMEA sentences, parse with `pynmea2`,
    extract lat/lon/altitude, return SensorReading with GPSPosition in metadata
  - `_read_mock()`: use MockManager for lat/lon, generate a slow walk pattern
    around base coordinates, include fix_quality="simulated"
  - `get_position() -> GPSPosition | None`: convenience method
  - `cleanup()`: close serial port

Tests: mock read returns GPSPosition, walk pattern moves, health_check,
cleanup, read twice, fix_quality field.

### Prompt 1.3 — GPS Module (continued)

Tests (continued): mock read returns GPSPosition, walk pattern moves,
health_check, cleanup, read twice, fix_quality field.

### Prompt 1.4 — Temperature/Humidity Sensor

Create `src/sensors/temp_humidity.py` and `tests/test_temp_humidity.py`.

- `TempHumiditySensor(SensorBase)` class:
  - `name = "temp_humidity"`, `metrics = ["temp_c", "humidity_pct"]`,
    `bus_type = "i2c"`
  - Constructor: `(config: TempHumidityConfig | None = None, mock_mode: bool = False)`
  - `_init_hardware()`: try import `sht40` or `adafruit_sht4x`, set up I2C at 0x44
  - `_read_hardware()`: read temp and humidity, return SensorReading
  - `_read_mock()`: use MockManager with diurnal cycle for temp/humidity
  - `classify_temp(value) -> str`: "cold" (<15), "mild" (15-28), "hot" (>28)
  - `classify_humidity(value) -> str`: "dry" (<40), "comfortable" (40-70), "humid" (>70)

Tests: mock read, classify thresholds, health_check, diurnal variation,
cleanup, read twice.

### Prompt 1.5 — Light Sensor

Create `src/sensors/light_sensor.py` and `tests/test_light_sensor.py`.

- `LightSensor(SensorBase)` class:
  - `name = "light"`, `metrics = ["light_lux"]`, `bus_type = "adc"`
  - Constructor: `(config: LightConfig | None = None, mock_mode: bool = False)`
  - `_init_hardware()`: try import ADC library, set up channel 2
  - `_read_hardware()`: read ADC, convert voltage to lux via log curve
    (0V = 0 lux, 3.3V ≈ 100,000 lux, log scale)
  - `_read_mock()`: use MockManager, diurnal cycle (full sun day, ~0 at night)
  - `classify(value) -> str`: "night" (<10), "dawn_dusk" (10-500), "overcast"
    (500-10000), "daylight" (10000-50000), "bright" (>50000)
  - `is_night() -> bool`: convenience, `light_lux < night_lux_threshold`

Tests: mock read, classify thresholds, is_night, diurnal variation,
health_check, cleanup, read twice.

### Prompt 1.6 — IMU Sensor

Create `src/sensors/imu.py` and `tests/test_imu.py`.

- `IMUSensor(SensorBase)` class:
  - `name = "imu"`, `metrics = ["accel_x", "accel_y", "accel_z"]`,
    `bus_type = "i2c"`
  - Constructor: `(config: IMUConfig | None = None, mock_mode: bool = False)`
  - `_init_hardware()`: try import `mpu6050` or `adafruit_mpu6050`, I2C at 0x68
  - `_read_hardware()`: read 3-axis acceleration, return SensorReading
  - `_read_mock()`: use MockManager, gravity on Z (9.81), slight sway on X/Y
  - `is_moving(threshold=0.5) -> bool`: check if |accel| - gravity > threshold
  - `get_orientation() -> str`: "upright", "tilted", "inverted", "flat"
    based on which axis is dominant

Tests: mock read, is_moving threshold, get_orientation, health_check,
cleanup, read twice.

---

## Phase 2: Harvest Modules (Each delegated to 1 subagent)

### Prompt 2.1 — Avocado Harvest Module

Create `src/modules/avocado.py` and `tests/test_avocado.py`.

- `AvocadoHarvest` class:
  - Tracks avocado harvest entries (count, weight, location, tree_id)
  - `log_harvest(count, weight_kg, location, tree_id=None, notes="") -> HarvestEntry`
  - `daily_summary(date=None) -> dict`: total count, total weight, avg per tree,
    trees visited
  - `quality_assessment(reading: SensorReading) -> str`: given soil moisture +
    pH readings, return ripeness guidance for avocado trees
    ("optimal conditions for harvest", "soil too dry — irrigate before harvest",
    "pH too low — amend soil")
  - `harvest_window(gps_positions: list[GPSPosition]) -> dict`: given recent
    GPS track, estimate area covered and suggest next tree
  - Stores entries in SQLite (use `sqlite3` stdlib)
  - `to_dict()` and `from_dict()` on HarvestEntry (in types.py)
  - All methods mock-safe (no hardware dependency)

Tests: log_harvest, daily_summary, quality_assessment with dry/moist/wet soil
and acidic/optimal/alkaline pH, harvest_window with GPS positions, SQLite
persistence round-trip, empty daily summary.

### Prompt 2.2 — Orange Harvest Module

Create `src/modules/orange.py` and `tests/test_orange.py`.

- `OrangeHarvest` class: same interface as AvocadoHarvest but orange-specific:
  - `log_harvest`, `daily_summary`, `quality_assessment`, `harvest_window`
  - Quality assessment thresholds: orange prefers pH 5.5-6.5, moisture 40-70%
  - "optimal conditions for citrus harvest", "moisture too low for citrus",
    "pH outside citrus range (5.5-6.5)"
  - SQLite storage
  - `brix_estimate(reading) -> float | None`: rough sugar content estimate from
    temp + moisture (placeholder formula, clearly documented as approximate)

Tests: log_harvest, daily_summary, quality_assessment with various soil
conditions, brix_estimate, SQLite persistence, empty summary.

### Prompt 2.3 — Local Greens Module

Create `src/modules/greens.py` and `tests/test_greens.py`.

- `GreensHarvest` class: same interface for local greens (sukuma wiki/kale,
  spinach, managu/African nightshade):
  - `log_harvest`, `daily_summary`, `quality_assessment`, `harvest_window`
  - Quality assessment: greens prefer pH 6.0-7.0, moisture 50-80%
  - `crop_type` field on HarvestEntry: "kale", "spinach", "managu", "other"
  - `leaf_condition(temp_c, humidity_pct) -> str`: "good" (15-25°C, >50% humidity),
    "wilt_risk" (>28°C or <30% humidity), "frost_risk" (<5°C)
  - SQLite storage

Tests: log_harvest with different crop types, daily_summary, quality_assessment,
leaf_condition, SQLite persistence, empty summary.

---

## Phase 3: Engine + Recorder (Parent builds directly)

### Prompt 3.1 — Engine

Create `src/core/engine.py` and `tests/test_engine.py`.

- `Engine` class: central data aggregation and analysis:
  - Constructor: `(config: MainConfig, sensors: dict[str, SensorBase])`
  - `read_all() -> dict[str, SensorReading]`: poll all enabled sensors
  - `get_summary() -> dict`: aggregated sensor summary for prompt handlers
    - per-sensor: latest reading, classification, health
    - cross-sensor: is_day (from light), is_moving (from IMU), location (from GPS)
  - `get_trends(window_minutes=30) -> dict`: trend analysis over time window
    - rate of change for moisture, temp, humidity
    - position delta from GPS
  - `get_baselines() -> dict`: current baselines (rolling average)
  - `update_baselines()`: recalculate rolling averages
  - Thread-safe (RLock)

Tests: read_all in mock mode, get_summary shape, get_trends with mock data,
baselines update, thread safety.

### Prompt 3.2 — Recorder

Create `src/core/recorder.py` and `tests/test_recorder.py`.

- `Recorder` class: SQLite persistence for all sensor readings and events
  - Constructor: `(db_path: str = "data/agri_stick.db")`
  - `init_db()`: create tables (sensor_readings, harvest_entries, night_events, gps_track)
  - `record_reading(reading: SensorReading)`: insert into sensor_readings
  - `record_harvest(entry: HarvestEntry)`: insert into harvest_entries
  - `record_night_event(event: NightEvent)`: insert into night_events
  - `record_gps(position: GPSPosition)`: insert into gps_track
  - `query_readings(sensor_name, start_time, end_time) -> list[dict]`
  - `query_harvests(crop, date=None) -> list[dict]`
  - `query_night_events(start_time, end_time) -> list[dict]`
  - `query_gps_track(start_time, end_time) -> list[dict]`
  - `close()`
  - SQLite with `:memory:` support for tests, `check_same_thread=False`
  - Parameterized queries (no SQL injection)
  - Auto-create `data/` directory if it doesn't exist

Tests: init_db, record/query each entity type, parameterized query safety,
memory mode, close, concurrent writes.

---

## Phase 4: Prompts + Night Mode (Parent builds directly)

### Prompt 4.1 — Prompts (Question Handlers)

Create `src/core/prompts.py` and `tests/test_prompts.py`.

- Deterministic prompt handlers (no LLM, no hardware):
  - `handle_soil_status(summary: dict) -> str`: "Soil moisture is X%, classified
    as Y. pH is Z, classified as W."
  - `handle_harvest_advice(summary: dict, crop: str) -> str`: crop-specific
    advice using the harvest module's quality_assessment
  - `handle_location(summary: dict) -> str`: "You are at lat X, lon Y.
    Altitude Z meters. Fix quality: W."
  - `handle_weather(summary: dict) -> str`: temp, humidity, light conditions
  - `handle_day_night(summary: dict) -> str`: day/night status, light level
  - `handle_walk_summary(summary: dict, trends: dict) -> str`: distance walked,
    area covered, movement status
  - `handle_night_report(events: list[dict]) -> str`: summary of night events
  - `handle_health(summary: dict) -> str`: sensor health summary
  - Each handler is a pure function: `handler(summary_or_data) -> str`
  - Fixtures in `tests/fixtures.py` for each handler

Tests: each handler with fixture data, edge cases (missing sensors, null readings),
non-alarmist framing (awareness tool, not medical instrument).

### Prompt 4.2 — Night Mode Sentinel

Create `src/modules/night_mode.py` and `tests/test_night_mode.py`.

- `NightModeSentinel` class:
  - Constructor: `(config: NightModeConfig, sensors: dict, event_bus: EventBus,
    recorder: Recorder)`
  - `start()`: begin background polling thread
  - `stop()`: stop polling, join thread
  - `_poll_loop()`: every `poll_interval_s`:
    - Read light sensor → if below threshold, enter night mode
    - Read IMU → if motion detected above threshold, emit NIGHT_ALERT event
    - Read GPS → log position
    - Record all readings to Recorder
  - `is_active() -> bool`: currently in night mode
  - `get_events() -> list[NightEvent]`: recent night events
  - `classify_motion(accel_magnitude) -> str`: "none", "small_animal",
    "human", "large_animal" (threshold-based, clearly documented as approximate)
  - Thread-safe, graceful shutdown via threading.Event
  - In mock mode: simulate night by using mock light sensor returning <10 lux

Tests: start/stop, mock night detection, motion alert emission, event recording,
classify_motion thresholds, thread safety, double-start protection.

---

## Phase 5: Dashboard + CLI (Parent builds directly)

### Prompt 5.1 — Dashboard

Create `src/core/dashboard.py` and `tests/test_dashboard.py`.

- `DashboardService` class:
  - FastAPI app (if available) with endpoints:
    - `GET /` → self-contained HTML dashboard page
    - `GET /api/state` → current sensor summary
    - `GET /api/history/{sensor_name}` → recent readings
    - `GET /api/harvest/{crop}` → harvest entries
    - `GET /api/night/events` → night mode events
    - `GET /api/health` → system health
    - `GET /eink.png` → 1-bit PNG for e-ink display (400×300)
  - Background thread reads sensors via Engine and updates DashboardState
  - Thread-safe state with RLock
  - HTML: single page, no external assets, auto-refresh, dark theme, mobile-friendly
  - Falls back to stdlib `http.server` if FastAPI not installed

Tests: FastAPI TestClient (if available), state endpoint, history endpoint,
health endpoint, HTML rendering, e-ink PNG generation (Pillow if available).

### Prompt 5.2 — CLI

Create `src/core/cli.py` and `tests/test_cli.py`.

- `CLI` class: interactive terminal loop:
  - `start()`: print banner, enter read-eval loop
  - Commands: `soil`, `ph`, `weather`, `location`, `harvest <crop> <count>
    <weight>`, `night`, `health`, `summary`, `help`, `quit`
  - Each command calls the appropriate prompt handler
  - `--mock` flag forces mock mode for all sensors
  - `--config <path>` loads YAML config
  - `--dashboard` starts dashboard server in background thread
  - No external dependencies beyond stdlib

Tests: command dispatch, mock mode flag, help text, each command output,
quit handling.

---

## Phase 6: Orchestrator + Hardware Docs (Parent builds directly)

### Prompt 6.1 — Main Orchestrator

Create `src/main.py` and `tests/test_main.py`.

- `AgriStickAgent` class:
  - Constructor: `(config: MainConfig)` — initializes all sensors, engine,
    recorder, event bus, harvest modules, night mode, dashboard, CLI
  - `start()`: initialize sensors, start recorder, start engine polling,
    start night mode (if enabled), start dashboard (if enabled)
  - `stop()`: graceful shutdown in reverse order
  - `run_cli()`: start agent then enter CLI loop
  - `run_dashboard()`: start agent then serve dashboard
  - `run_daemon()`: start agent as a background daemon (no CLI)
  - Startup order: storage → sensors → engine → recorder → night mode →
    dashboard → CLI
  - Shutdown order: CLI → dashboard → night mode → recorder → engine →
    sensors → storage

Tests: mock-mode startup/shutdown, component initialization order, health
check, daemon mode.

### Prompt 6.2 — Hardware Documentation

Create `hardware/` directory with:

- `parts_list.md`: BOM table with Pi Zero 2 W, sensors, battery, enclosure,
  walking stick mount. Budget and recommended columns. Total weight estimate.
- `wiring.md`: ASCII GPIO pinout, I2C/ADC/SPI/UART assignments, config.txt
  settings, first-time checklist, verification commands
- `sensor_guide.md`: sensor placement on the walking stick, probe depth
  for soil sensors at the tip, GPS antenna orientation, weight distribution,
  waterproofing for soil probe section
- `stick_design.md`: physical design notes — stick material, sensor housing,
  battery placement, cable routing, weight budget (<1 kg total electronics),
  detachable probe tip

---

## Phase 7: Integration Testing

### Prompt 7.1 — Full Test Suite

Run `python -m pytest tests/ -v` and fix all failures. Target: 200+ tests.

Categories:
- `test_types.py` (~10 tests)
- `test_config.py` (~10 tests)
- `test_sensor_base.py` (~8 tests)
- `test_mock_manager.py` (~10 tests)
- `test_event_bus.py` (~8 tests)
- `test_soil_moisture.py` (~10 tests)
- `test_soil_ph.py` (~10 tests)
- `test_gps.py` (~12 tests)
- `test_temp_humidity.py` (~12 tests)
- `test_light_sensor.py` (~12 tests)
- `test_imu.py` (~12 tests)
- `test_avocado.py` (~12 tests)
- `test_orange.py` (~12 tests)
- `test_greens.py` (~12 tests)
- `test_engine.py` (~10 tests)
- `test_recorder.py` (~12 tests)
- `test_prompts.py` (~15 tests)
- `test_night_mode.py` (~12 tests)
- `test_dashboard.py` (~10 tests)
- `test_cli.py` (~10 tests)
- `test_main.py` (~8 tests)

Total target: ~209 tests

---

## Testing Strategy

- **Mock mode first**: every sensor and module runs in mock mode with no hardware
- **Fixtures**: `tests/fixtures.py` contains realistic sensor data for prompt handlers
- **SQLite :memory:**: recorder tests use in-memory database
- **No network**: GPS, dashboard, and night mode tests use mock data only
- **Optional imports**: FastAPI, Pillow, serial, I2C libraries all have graceful
  fallback to stdlib or mock
- **Thread safety**: concurrent access tests for Engine, Recorder, EventBus, NightMode
- **Non-alarmist framing**: prompt handlers use awareness language, not medical claims