# Project State: Terra-Fin Agent

> **Last updated:** 2026-08-02
> **Current phase:** ESP32 port complete
> **Overall health:** green

---

## 1. Goal (1–2 sentences)

A lightweight agricultural companion agent on an ESP32 attached to a walking stick, accompanying Kenyan farmers through avocado, orange, and local greens harvests with soil sensors, GPS, weather, cellular telemetry, and night-mode security. Ported from Raspberry Pi Zero 2 W (CPython) to ESP32 (MicroPython) for cost (~$43 vs ~$65) and power efficiency.

## 2. Current Status

### Done
- [x] Project directory structure created
- [x] PROMPTS.md written (testable build prompts for all phases)
- [x] Project_state.md scaffolded
- [x] Phase 0: Core foundation (types, config, sensor_base, mock_manager, event_bus)
- [x] Phase 1: Sensor modules (7 sensors)
- [x] Phase 2: Harvest modules (avocado, orange, greens)
- [x] Phase 3: Engine + Recorder
- [x] Phase 4: Prompts + Night Mode
- [x] Phase 5: Dashboard + CLI
- [x] Phase 6: Main orchestrator + hardware docs
- [x] Full Pi test suite passing (613 tests)
- [x] README written
- [x] Cellular module: CellularConfig, CellularSensor driver, 38 tests
- [x] Shark-fin antenna enclosure design doc
- [x] Hardware docs updated (parts_list, stick_design, wiring, sensor_guide)
- [x] Committed locally (Pi version)

### ESP32 Port (Completed 2026-08-02)
- [x] All 59 ESP32 .py files compile clean
- [x] 30 adaptation modules ported (union types stripped, typing removed)
- [x] 7 sensor drivers rewritten (machine.ADC/I2C/UART/Pin, mock-safe)
- [x] Core infrastructure (types, config, engine, recorder, event_bus, adaptation_base, adaptation_manager)
- [x] Harvest modules (avocado, orange, greens) rewritten with JSON persistence (no sqlite3)
- [x] Night mode sentinel rewritten (_thread instead of threading)
- [x] Dashboard + CLI rewritten for MicroPython
- [x] ESP32 main.py entry point written
- [x] 77 ESP32 tests passing (all green)
- [x] ESP32 README with pinout, BOM, flash instructions
- [x] Temp cleanup scripts deleted
- [x] MicroPython compatibility verified (no __future__, no sqlite3, no union types)

### In Progress
- [ ] Commit and push ESP32 port to GitHub origin main

### Not Started
- [ ] Shark-fin 3D model (OpenSCAD parametric file)
- [ ] CLI `signal` command implementation
- [ ] Upload integration (event-driven data sync via cellular)
- [ ] ESP32 field testing with real hardware

## 3. Architecture & Key Decisions

| Decision | Rationale | Date |
|---|---|---|
| Pi Zero 2 W as compute platform | Lightweight, low-power, sufficient for sensor polling + CLI | 2026-07-24 |
| **ESP32 replaces Pi Zero** | **~$43 vs ~$65, lower power, MicroPython built-in, no OS overhead** | **2026-08-02** |
| Walking stick form factor | Farmer already carries one; sensors at tip (soil) + shaft (air) | 2026-07-24 |
| Mock-safe sensor architecture | Dev/test without hardware, same code paths | 2026-07-24 |
| Deterministic prompt handlers (no LLM) | ESP32/Pi can't run LLM; handlers are pure functions | 2026-07-24 |
| Night mode as sentinel daemon | Stationary stick records motion, GPS, environmental data at night | 2026-07-24 |
| **JSON/JSONL persistence (ESP32)** | **MicroPython has no sqlite3; JSON is zero-config, inspectable** | **2026-08-02** |
| **_thread instead of threading (ESP32)** | **MicroPython has _thread module, not threading** | **2026-08-02** |
| EventBus (_thread locks) | No asyncio dependency, simpler on ESP32 | 2026-07-24 |
| SIM7600G-H cellular modem | 4G LTE Cat-1, built-in GNSS, USB serial, AT commands, Kenya-compatible | 2026-07-24 |
| Shark-fin antenna enclosure | Omnidirectional, sky-facing, snag-resistant, houses LTE + GNSS antennas | 2026-07-24 |

## 4. Blockers & Risks

- **Risk:** Sensor calibration curves are approximations → Documented in code, user can refine with real hardware data
- **Risk:** Night mode motion classification is threshold-based → Clearly documented as approximate, not a security system
- **Risk:** SIM7600 power draw (500 mA TX peaks) may exceed ESP32 power → Dedicated power supply recommended
- **Risk:** Cellular data costs money → upload_enabled defaults to False; user opts in
- **Risk:** ESP32 ADC1 accuracy (12-bit, ~0-3.3V) → Adequate for soil moisture/pH awareness, not precision

## 5. Next Step

> **Next:** Commit and push ESP32 port to GitHub origin main. Then implement `signal` CLI command and event-driven upload integration.

## 6. Environment & Tooling Notes

- **Pi version:** Python 3.10+, pyyaml, FastAPI (optional), Pillow (optional)
- **ESP32 version:** MicroPython v1.23+, machine module, _thread, JSON persistence
- Hardware deps (Pi optional): RPi.GPIO, adafruit_mcp3xxx, adafruit_sht4x, mpu6050, pynmea2, pyserial
- Hardware deps (ESP32): machine module (built-in), no external libs needed
- Deployment targets: Raspberry Pi Zero 2 W (src/) or ESP32 (esp32/)
- ESP32 test suite: 77 tests using fake_machine stub (CPython-compatible)
- Hermes skills used: edge-deployment-workflows, software-development-workflows, project-state-management

## 7. Recent Session Log

- 2026-07-24: Project created, all phases built, 613 Pi tests passing, committed locally
- 2026-07-24: Cellular module + shark-fin antenna added, 613 tests passing
- 2026-08-02: ESP32 port completed — 59 files, 77 tests, all green

## 8. References

- Build prompts: `PROMPTS.md`
- Hardware docs: `hardware/`
- Shark-fin antenna design: `hardware/shark_fin_antenna.md`
- ESP32 port: `esp32/` (README, lib/, tests/)