# Terra-Fin Agent — ESP32 / MicroPython Port

An agricultural walking stick agent for Kenyan smallholder farmers, ported
from Raspberry Pi (CPython) to ESP32 (MicroPython) for cost and power efficiency.

## Overview

The ESP32 port retains all functionality from the Pi Zero version:
- **7 sensors** (soil moisture, soil pH, light, temp/humidity, GPS, IMU, cellular)
- **30 adaptation modules** (weather, soil, animal/insect monitoring)
- **Harvest tracking** (avocado, orange, greens) with JSON persistence
- **Night mode sentinel** for stationary monitoring
- **HTTP dashboard** accessible from a phone
- **Mock-safe architecture** — works without any hardware connected

## ESP32 Pin Assignments

```
┌─────────────────────────────────────────────────────┐
│  ESP32 Pin Assignment — Terra-Fin Agent             │
├─────────────────┬──────────┬─────────────────────────┤
│  Sensor         │  ESP32   │  Notes                  │
├─────────────────┼──────────┼─────────────────────────┤
│  Soil Moisture  │  GPIO32  │  ADC1_CH4 (capacitive)  │
│  Soil pH        │  GPIO33  │  ADC1_CH5               │
│  Light          │  GPIO34  │  ADC1_CH6 (input only)  │
│  Temp/Humidity  │  I2C     │  SHT40 (SDA=21, SCL=22) │
│  GPS            │  UART2   │  TX=GPIO17, RX=GPIO16   │
│  IMU            │  I2C     │  MPU-6050 (addr 0x68)   │
│  Cellular       │  UART1   │  SIM7600 (TX=9, RX=10)  │
│  (I2C SDA)      │  GPIO21  │  Shared I2C bus         │
│  (I2C SCL)      │  GPIO22  │  Shared I2C bus         │
└─────────────────┴──────────┴─────────────────────────┘
```

## Directory Structure

```
esp32/
├── main.py              # Top-level entry point (flash to ESP32 root)
├── lib/
│   ├── main.py          # Agent bootstrap + main loop
│   ├── core/
│   │   ├── types.py         # SensorReading, HarvestEntry, NightEvent, etc.
│   │   ├── config.py        # MainConfig and sensor configs
│   │   ├── sensor_base.py   # SensorBase with _make_lock() pattern
│   │   ├── mock_manager.py  # Diurnal mock data generator
│   │   ├── event_bus.py     # Pub/sub event bus
│   │   ├── engine.py        # Sensor aggregation + trend analysis
│   │   ├── recorder.py      # JSONL persistence (replaces sqlite3)
│   │   ├── adaptation_base.py  # Base class for 30 modules
│   │   ├── adaptation_manager.py  # Orchestrates all modules
│   │   ├── prompts.py       # Deterministic prompt handlers
│   │   ├── cli.py            # Interactive CLI (REPL)
│   │   └── dashboard.py     # HTTP dashboard server
│   ├── sensors/
│   │   ├── soil_moisture.py  # Capacitive probe (ADC)
│   │   ├── soil_ph.py        # pH probe (ADC)
│   │   ├── light_sensor.py   # LUX sensor (ADC)
│   │   ├── temp_humidity.py  # SHT40 (I2C)
│   │   ├── gps.py            # NMEA GPS (UART)
│   │   ├── imu.py            # MPU-6050 (I2C)
│   │   └── cellular.py       # SIM7600G-H modem (UART)
│   ├── modules/
│   │   ├── avocado.py        # Avocado harvest tracker (JSON)
│   │   ├── orange.py         # Orange harvest tracker (JSON)
│   │   ├── greens.py         # Greens harvest tracker (JSON)
│   │   └── night_mode.py     # Night sentinel (motion detection)
│   └── adaptation/
│       └── (30 modules)      # Weather, soil, animal/insect advisories
├── tests/
│   ├── fake_machine.py   # Mock MicroPython `machine` module
│   └── test_port.py      # Comprehensive test suite
└── README.md             # This file
```

## Key Changes from Pi Zero Version

| Aspect | Pi Zero (CPython) | ESP32 (MicroPython) |
|--------|-------------------|----------------------|
| Persistence | sqlite3 | JSON / JSONL files |
| Threading | threading.Lock/Thread | _thread.allocate_lock + start_new_thread |
| Data structures | collections.deque | Plain lists with manual trimming |
| Type annotations | Python 3.10+ (X \| Y) | Removed (not supported) |
| Path handling | pathlib | String paths |
| Dates | datetime module | time.gmtime() via utc_now() |
| Hardware I/O | RPi.GPIO, adafruit libs | machine.ADC/I2C/UART/Pin |
| GPS parsing | pynmea2 | Manual NMEA parsing |

## Mock-Safe Architecture

Every sensor uses `try/except ImportError` for the `machine` module.
When hardware is unavailable (development on desktop, or sensor disconnected),
sensors fall back to mock mode using `MockManager` which generates realistic
diurnal cycles for temperature, humidity, light, soil moisture, and GPS.

This means you can:
- Develop and test on any computer with CPython
- Flash to ESP32 and it auto-detects hardware
- Run with partial sensor arrays (only connected sensors are active)

## Running Tests (on CPython)

```bash
cd ~/projects/terra-fin/esp32
python3 -m pytest tests/test_port.py -v

# Or without pytest:
python3 tests/test_port.py
```

Tests use `fake_machine.py` to stub the MicroPython `machine` module,
so all sensor code runs on standard CPython.

## Flashing to ESP32

1. **Install MicroPython** (v1.23+ recommended):
   ```bash
   esptool.py --port /dev/ttyUSB0 erase_flash
   esptool.py --port /dev/ttyUSB0 write_flash 0x0 esp32-20240602-v1.23.0.bin
   ```

2. **Copy files** using `mpremote` or `rshell`:
   ```bash
   mpremote cp -r lib/ :/lib/
   mpremote cp main.py :/main.py
   ```

3. **Create data directory** on the ESP32:
   ```bash
   mpremote mkdir /flash/data/terra-fin
   ```

4. **Reboot** — the agent starts automatically if `main.py` is in the root.

## Configuration

The agent loads `MainConfig` defaults on startup. To customize:
- Edit `/lib/core/config.py` before flashing, or
- Create a `/flash/data/terra-fin/config.json` file on the ESP32.

Key settings:
- `mock_mode`: If true, all sensors use mock data (default: true)
- `dashboard.port`: HTTP dashboard port (default: 8080)
- `cellular.upload_enabled`: Enable cellular data upload (default: false)
- `night_mode.enabled`: Enable night sentinel (default: true)

## Hardware Bill of Materials

| Component | Part | Est. Cost (USD) |
|-----------|------|-----------------|
| MCU | ESP32 DevKit V1 | $5 |
| Soil moisture | Capacitive soil sensor v1.2 | $2 |
| Soil pH | Analog pH probe + module | $8 |
| Light | LDR or BH1750 | $1 |
| Temp/Humidity | SHT40 breakout | $3 |
| GPS | NEO-6M module | $5 |
| IMU | MPU-6050 breakout | $2 |
| Cellular | SIM7600G-H module | $12 |
| Power | 18650 battery + holder | $3 |
| Walking stick | Bamboo/wood stick | $2 |
| **Total** | | **~$43** |

Compare to Pi Zero 2 W version: ~$65+ (Pi + sensors + SD card + power).

## Sensor Wiring Notes

- **ADC pins**: ESP32 ADC1 (GPIO32-39) is used because ADC2 conflicts with WiFi.
- **I2C bus**: Shared between SHT40 (temp/humidity) and MPU-6050 (IMU).
- **UART**: GPS on UART2 (GPIO16/17), Cellular on UART1 (GPIO9/10).
  UART0 is reserved for USB REPL.
- **Capacitive soil probe**: Must NOT be fully submerged — only the probe tip.
- **GPS antenna**: Place at the top of the stick for best sky visibility.
- **Cellular antenna**: Shark-fin style on the stick shaft.

## License & Acknowledgments

Part of the Terra-Fin project. Built for Kenyan smallholder farmers.
GitHub: drwjkirkpatrick-web/terra-fin