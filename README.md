# Terra-Fin Agent

A lightweight agricultural companion agent mounted on a walking stick,
accompanying Kenyan farmers through avocado, orange, and local greens
harvests. Runs on either a **Raspberry Pi Zero 2 W** (CPython) or an
**ESP32** (MicroPython) — your choice of platform.

## What It Does

- **Soil monitoring:** Moisture and pH readings from a probe at the stick tip
- **Location tracking:** GPS for harvest mapping and walking distance
- **Weather awareness:** Temperature, humidity, and ambient light
- **Motion detection:** IMU for walking vs stationary detection
- **Cellular telemetry:** 4G LTE modem with shark-fin antenna for field data upload
- **Harvest logging:** Track count, weight, and location for each crop
- **Night sentinel:** When the stick is stationary at night, it monitors for
  motion and logs environmental data
- **30 adaptation modules:** Weather, soil, and animal/insect advisories that
  help the farmer respond to changing conditions
- **Dashboard:** Simple web interface accessible from a phone on local WiFi

## Two Platforms, One Codebase

The project ships in two parallel implementations sharing the same
architecture and business logic:

| | Raspberry Pi Zero 2 W | ESP32 |
|---|---|---|
| **Language** | Python 3.10+ | MicroPython v1.23+ |
| **Location** | `src/` | `esp32/lib/` |
| **Persistence** | SQLite3 | JSON / JSONL files |
| **Threading** | `threading` (RLock, Thread) | `_thread` (allocate_lock) |
| **Hardware I/O** | RPi.GPIO, Adafruit CircuitPython | `machine` module (ADC, I2C, UART) |
| **GPS parsing** | pynmea2 | Manual NMEA parser |
| **Tests** | 613 (pytest) | 77 (unittest + fake\_machine) |
| **Cost** | ~$109 budget / ~$243 recommended | ~$43 |
| **Runtime** | ~25–40 h (10,000 mAh bank) | ~40+ h (18650 cell) |

Both platforms are **mock-safe** — every sensor falls back to mock data
when hardware is absent, so you can develop and test on any computer.

### Which should I use?

- **Pi Zero 2 W** — more compute headroom, easier to debug over SSH,
  standard Python ecosystem (pip, pytest), WiFi built in. Best for
  development and when you need the full dashboard + CLI on-device.
- **ESP32** — lower cost ($43 vs $109+), lower power, smaller footprint,
  no OS overhead. Best for production deployment where cost per unit
  matters (e.g. deploying across multiple farms).

## Hardware

### Common Sensors (both platforms)

- Capacitive soil moisture probe (ADC)
- pH probe (ADC)
- GPS module (NEO-6M / NEO-M8N)
- SHT40 temperature/humidity (I2C)
- Light sensor (LDR or BH1750, ADC)
- MPU-6050 IMU (I2C)
- SIM7600G-H cellular modem (UART)

### Pi Zero 2 W Specifics

- **Antenna:** Shark-fin enclosure (3D-printed PETG) with LTE + GNSS patch antennas
- **Power:** 10,000 mAh USB power bank (~25–40 hours runtime)
- **Weight:** ~878 g electronics, ~1.4 kg total with stick
- See `hardware/` for full parts list, wiring guide, sensor placement,
  and stick design notes.

### ESP32 Specifics

- **ADC:** GPIO32 (moisture), GPIO33 (pH), GPIO34 (light) — ADC1 only
- **I2C:** SDA=GPIO21, SCL=GPIO22 (shared SHT40 + MPU-6050)
- **UART:** GPS on UART2 (GPIO16/17), Cellular on UART1 (GPIO9/10)
- **Power:** Single 18650 cell (~40+ hours)
- See `esp32/README.md` for pinout table, BOM, and flash instructions.

## Software Architecture

### Pi Zero (src/)

```
src/
├── core/
│   ├── types.py          # Shared dataclasses (SensorReading, HarvestEntry, etc.)
│   ├── config.py         # YAML/env config with all sensor sub-configs
│   ├── sensor_base.py    # Abstract SensorBase with mock-safe hardware fallback
│   ├── mock_manager.py   # Time-varying mock data (diurnal cycles)
│   ├── event_bus.py      # Thread-safe pub/sub
│   ├── engine.py         # Sensor aggregation, trends, baselines
│   ├── recorder.py       # SQLite persistence (all readings, harvests, events)
│   ├── prompts.py        # Deterministic plain-English handlers (no LLM)
│   ├── dashboard.py      # Stdlib HTTP dashboard (no external deps)
│   └── cli.py            # Interactive terminal interface
├── sensors/
│   ├── soil_moisture.py  # Capacitive moisture probe (ADC)
│   ├── soil_ph.py        # pH probe (ADC)
│   ├── gps.py            # GPS module (USB UART)
│   ├── temp_humidity.py  # SHT40 (I2C)
│   ├── light_sensor.py   # LDR (ADC)
│   ├── imu.py            # MPU-6050 (I2C)
│   └── cellular.py       # SIM7600 cellular modem (USB UART, AT commands)
├── modules/
│   ├── avocado.py        # Avocado harvest tracking + quality assessment
│   ├── orange.py         # Orange harvest tracking + Brix estimate
│   ├── greens.py         # Local greens (kale, spinach, managu) tracking
│   └── night_mode.py     # Night sentinel: motion detection + GPS logging
├── adaptation/            # 30 adaptation modules (weather/soil/animal/insect)
│   ├── rain_predictor.py          # Rain likelihood from humidity + temp trends
│   ├── temperature_trend.py       # Rapid temperature shift warnings
│   ├── humidity_comfort.py        # Humidity for crop work + fungal risk
│   ├── wind_estimator.py          # Wind from stick sway (approximate)
│   ├── frost_alert.py             # Frost risk from temp + time of day
│   ├── drought_monitor.py         # Soil moisture drought tracking
│   ├── solar_radiation.py         # Solar radiation from lux (approximate)
│   ├── growing_degree_days.py    # GDD accumulation for crop development
│   ├── et_estimator.py            # Evapotranspiration for irrigation planning
│   ├── soil_moisture_trend.py     # Moisture rate of change → irrigation timing
│   ├── ph_drift_tracker.py        # pH drift → acidification/alkalinization
│   ├── nutrient_depletion.py      # N-P-K removal from harvest
│   ├── compaction_detector.py     # Soil compaction from moisture + resistance
│   ├── erosion_risk.py            # Erosion from rain + slope
│   ├── irrigation_scheduler.py    # Irrigation timing from moisture + ET + rain
│   ├── soil_temp_tracker.py       # Soil temp for germination + root health
│   ├── mulch_advisor.py           # Mulch recommendations from moisture + temp
│   ├── cover_crop_advisor.py      # Cover crop species by season + soil
│   ├── compost_timing.py          # Compost application timing
│   ├── pest_pressure.py           # Pest activity from temp + humidity + season
│   ├── pollinator_activity.py     # Pollination conditions from temp + light
│   ├── bird_scavenger.py          # Bird pressure on ripe fruit by time of day
│   ├── insect_phenology.py        # Insect development stages via pest GDD
│   ├── beneficial_insects.py      # Beneficial insect habitat quality
│   ├── grazing_pressure.py        # Livestock grazing from GPS track + cover
│   ├── rodent_activity.py         # Rodent activity from night motion events
│   ├── snake_alert.py             # Snake presence likelihood from temp + cover
│   ├── livestock_proximity.py     # Nearby livestock from motion patterns
│   ├── crop_disease_risk.py       # Fungal disease from humidity + leaf wetness
│   └── harvest_readiness.py       # Multi-factor harvest readiness integration
└── main.py               # Orchestrator (lifecycle management)
```

### ESP32 (esp32/lib/)

Same architecture, adapted for MicroPython:

```
esp32/
├── main.py              # Top-level entry point (flash to ESP32 root)
├── README.md            # ESP32 pinout, BOM, flash instructions
├── lib/
│   ├── main.py          # TerraFinAgent bootstrap + main loop
│   ├── core/            # types, config, engine, recorder (JSONL),
│   │                    # event_bus, adaptation_base, adaptation_manager,
│   │                    # prompts, cli, dashboard, mock_manager, sensor_base
│   ├── sensors/         # 7 drivers using machine.ADC/I2C/UART/Pin
│   ├── modules/         # avocado, orange, greens (JSON), night_mode
│   └── adaptation/      # 30 modules (same logic, no type annotations)
└── tests/
    ├── fake_machine.py  # Mock MicroPython `machine` module for CPython
    └── test_port.py     # 77 tests (all green)
```

Key differences from the Pi version: no `sqlite3` (JSON/JSONL persistence),
no `threading` (uses `_thread`), no `datetime` (uses `time.gmtime`),
no `deque` (plain lists), no `pathlib` (string paths), no type annotations.

## Quick Start

### Development (no hardware needed)

```bash
# Pi version — run the test suite (613 tests, all mock-mode)
python -m pytest tests/ -v

# ESP32 version — run the test suite (77 tests)
cd esp32 && python -m pytest tests/test_port.py -v

# Pi — start the CLI in mock mode
python -m src.main --mock

# Pi — start the dashboard
python -m src.main --mock --dashboard

# Pi — run as a daemon
python -m src.main --mock --daemon
```

### On the Pi Zero

```bash
# Install dependencies
pip install pyyaml

# Enable I2C, SPI, and UART
sudo raspi-config  # Interface Options

# Verify hardware
sudo i2cdetect -y 1   # Should show 0x44 and 0x68
ls /dev/spidev0.*     # Should show SPI devices
ls /dev/ttyACM0       # Should show GPS

# Run with real hardware
python -m src.main --config config.yaml
```

### On the ESP32

```bash
# Install MicroPython (v1.23+)
esptool.py --port /dev/ttyUSB0 erase_flash
esptool.py --port /dev/ttyUSB0 write_flash 0x0 esp32-20240602-v1.23.0.bin

# Copy files
mpremote cp -r lib/ :/lib/
mpremote cp main.py :/main.py

# Create data directory and reboot
mpremote mkdir /flash/data/terra-fin
```

See `esp32/README.md` for full pinout, BOM, and wiring details.

## CLI Commands

```
soil         - Show soil moisture and pH status
weather      - Show temperature, humidity, and light
location     - Show GPS location
signal       - Show cellular signal strength and network status
daynight     - Show day/night status
walk         - Show walking summary
harvest <crop> <count> <weight_kg> [tree_id] - Log a harvest
night        - Show night mode events
health       - Show sensor health
summary      - Show full sensor summary
adapt        - Show all adaptation advisories
adapt weather - Show weather adaptation advisories
adapt soil    - Show soil adaptation advisories
adapt animal - Show animal adaptation advisories
adapt insect - Show insect adaptation advisories
warnings     - Show only warning/critical advisories
help         - Show help
quit         - Exit
```

## Testing

### Pi version — 613 tests (all mock-mode, no hardware required)

```bash
python -m pytest tests/ -v
```

Test categories: types, config, sensor base, mock manager, event bus,
7 sensor drivers (incl. cellular), 3 harvest modules, engine, recorder,
prompts, night mode, dashboard, CLI, main orchestrator, and 30 adaptation
modules.

### ESP32 version — 77 tests (CPython with fake\_machine stubs)

```bash
cd esp32 && python -m pytest tests/test_port.py -v
```

Tests cover all core modules, 7 sensors (via fake\_machine), 10
representative adaptation modules, 3 harvest modules (JSON persistence),
night mode, and MicroPython compatibility checks (no `__future__`,
no `sqlite3`, all files compile).

## Design Principles

- **Mock-safe:** Every sensor runs in mock mode with no hardware attached
- **No LLM dependency:** Deterministic prompt handlers — works on Pi Zero and ESP32
- **Non-alarmist framing:** Awareness tool, not a medical or security instrument
- **Lightweight:** Stdlib-only dashboard, no external web framework required
- **Thread-safe:** All shared state uses locks (RLock on Pi, allocate\_lock on ESP32)
- **One agent per file:** Each module was written by a single author
- **Same logic, two targets:** Business logic is identical across platforms;
  only the I/O and persistence layers differ

## License

MIT

## Disclaimer

This is an awareness tool for agricultural guidance. It is not a medical
device, a security system, or a precision agricultural instrument. Use
certified meters for precise measurements and professional agricultural
extension services for crop management decisions.