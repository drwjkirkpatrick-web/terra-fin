# TerraFin Agent

A lightweight agricultural companion agent on a Raspberry Pi Zero 2 W,
mounted on a walking stick, accompanying Kenyan farmers through avocado,
orange, and local greens harvests.

## What It Does

- **Soil monitoring:** Moisture and pH readings from a probe at the stick tip
- **Location tracking:** GPS for harvest mapping and walking distance
- **Weather awareness:** Temperature, humidity, and ambient light
- **Motion detection:** IMU for walking vs stationary detection
- **Harvest logging:** Track count, weight, and location for each crop
- **Night sentinel:** When the stick is stationary at night, it monitors for
  motion and logs environmental data
- **Dashboard:** Simple web interface accessible from a phone on local WiFi

## Hardware

- **Platform:** Raspberry Pi Zero 2 W
- **Sensors:** Capacitive soil moisture, pH probe, GPS (NEO-M8N), SHT40
  (temp/humidity), LDR (light), MPU-6050 (IMU)
- **Power:** 10,000 mAh USB power bank (~25-40 hours runtime)
- **Weight:** ~815 g electronics, ~1.4 kg total with stick
- **Cost:** ~$91 budget / ~$193 recommended

See `hardware/` for full parts list, wiring guide, sensor placement,
and stick design notes.

## Software Architecture

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
│   └── imu.py            # MPU-6050 (I2C)
├── modules/
│   ├── avocado.py        # Avocado harvest tracking + quality assessment
│   ├── orange.py         # Orange harvest tracking + Brix estimate
│   ├── greens.py         # Local greens (kale, spinach, managu) tracking
│   └── night_mode.py     # Night sentinel: motion detection + GPS logging
└── main.py               # Orchestrator (lifecycle management)
```

## Quick Start

### Development (no hardware needed)

```bash
# Run the test suite (263 tests, all mock-mode)
python -m pytest tests/ -v

# Start the CLI in mock mode
python -m src.main --mock

# Start the dashboard
python -m src.main --mock --dashboard

# Run as a daemon
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

## CLI Commands

```
soil         - Show soil moisture and pH status
weather      - Show temperature, humidity, and light
location     - Show GPS location
daynight     - Show day/night status
walk         - Show walking summary
harvest <crop> <count> <weight_kg> [tree_id] - Log a harvest
night        - Show night mode events
health       - Show sensor health
summary      - Show full sensor summary
help         - Show help
quit         - Exit
```

## Testing

All 263 tests run in mock mode — no hardware required:

```bash
python -m pytest tests/ -v
```

Test categories: types, config, sensor base, mock manager, event bus,
6 sensor drivers, 3 harvest modules, engine, recorder, prompts, night mode,
dashboard, CLI, and main orchestrator.

## Design Principles

- **Mock-safe:** Every sensor runs in mock mode with no hardware attached
- **No LLM dependency:** Deterministic prompt handlers — works on Pi Zero
- **Non-alarmist framing:** Awareness tool, not a medical or security instrument
- **Lightweight:** Stdlib-only dashboard, no external web framework required
- **Thread-safe:** All shared state uses RLock, no asyncio complexity
- **One agent per file:** Each module was written by a single author

## License

MIT

## Disclaimer

This is an awareness tool for agricultural guidance. It is not a medical
device, a security system, or a precision agricultural instrument. Use
certified meters for precise measurements and professional agricultural
extension services for crop management decisions.