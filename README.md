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
- **30 adaptation modules:** Weather, soil, and animal/insect advisories that
  help the farmer respond to changing conditions
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

## Quick Start

### Development (no hardware needed)

```bash
# Run the test suite (575 tests, all mock-mode)
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

All 575 tests run in mock mode — no hardware required:

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