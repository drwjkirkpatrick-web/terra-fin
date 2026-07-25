# Project State: Terra-Fin Agent

> **Last updated:** 2026-07-24
> **Current phase:** build
> **Overall health:** green

---

## 1. Goal (1–2 sentences)

A lightweight agricultural companion agent on a Raspberry Pi Zero 2 W attached to a walking stick, accompanying Kenyan farmers through avocado, orange, and local greens harvests with soil sensors, GPS, weather, cellular telemetry, and night-mode security.

## 2. Current Status

### Done
- [x] Project directory structure created
- [x] PROMPTS.md written (testable build prompts for all phases)
- [x] Project_state.md scaffolded
- [x] Phase 0: Core foundation (types, config, sensor_base, mock_manager, event_bus)
- [x] Phase 1: Sensor modules (6 sensors)
- [x] Phase 2: Harvest modules (avocado, orange, greens)
- [x] Phase 3: Engine + Recorder
- [x] Phase 4: Prompts + Night Mode
- [x] Phase 5: Dashboard + CLI
- [x] Phase 6: Main orchestrator + hardware docs
- [x] Full test suite passing (613 tests)
- [x] README written
- [x] Cellular module: CellularConfig, CellularSensor driver, 38 tests
- [x] Shark-fin antenna enclosure design doc
- [x] Hardware docs updated (parts_list, stick_design, wiring, sensor_guide)
- [x] Committed locally

### In Progress
- [ ] Push to GitHub origin main

### Not Started
- [ ] Shark-fin 3D model (OpenSCAD parametric file)
- [ ] CLI `signal` command implementation (handler in prompts.py)
- [ ] Upload integration (event-driven data sync via cellular)

## 3. Architecture & Key Decisions

| Decision | Rationale | Date |
|---|---|---|
| Pi Zero 2 W as compute platform | Lightweight, low-power, sufficient for sensor polling + CLI | 2026-07-24 |
| Walking stick form factor | Farmer already carries one; sensors at tip (soil) + shaft (air) | 2026-07-24 |
| Mock-safe sensor architecture | Dev/test without hardware, same code paths | 2026-07-24 |
| Deterministic prompt handlers (no LLM) | Pi Zero can't run LLM; handlers are pure functions | 2026-07-24 |
| Night mode as sentinel daemon | Stationary stick records motion, GPS, environmental data at night | 2026-07-24 |
| SQLite for all persistence | Zero-config, stdlib, sufficient for single-device logging | 2026-07-24 |
| EventBus (threading-based) | No asyncio dependency, simpler on Pi Zero | 2026-07-24 |
| SIM7600G-H cellular modem | 4G LTE Cat-1, built-in GNSS, USB serial, AT commands, Kenya-compatible | 2026-07-24 |
| Shark-fin antenna enclosure | Omnidirectional, sky-facing, snag-resistant, houses LTE + GNSS antennas | 2026-07-24 |

## 4. Blockers & Risks

- **Risk:** Sensor calibration curves are approximations → Documented in code, user can refine with real hardware data
- **Risk:** Night mode motion classification is threshold-based → Clearly documented as approximate, not a security system
- **Risk:** SIM7600 power draw (500 mA TX peaks) may exceed Pi Zero USB → Dedicated USB port from power bank recommended
- **Risk:** Cellular data costs money → upload_enabled defaults to False; user opts in

## 5. Next Step

> **Next:** Push to GitHub origin main. Then implement `signal` CLI command and event-driven upload integration.

## 6. Environment & Tooling Notes

- Runtime: Python 3.10+
- Key deps: pyyaml (config), FastAPI (dashboard, optional), Pillow (e-ink, optional)
- Hardware deps (optional): RPi.GPIO, adafruit_mcp3xxx, adafruit_sht4x, mpu6050, pynmea2, pyserial
- Deployment target: Raspberry Pi Zero 2 W on walking stick
- Hermes skills used: edge-deployment-workflows, software-development-workflows, project-state-management

## 7. Recent Session Log

- 2026-07-24: Project created, all phases built, tests passing, committed locally
- 2026-07-24: Cellular module + shark-fin antenna added, 613 tests passing

## 8. References

- Build prompts: `PROMPTS.md`
- Hardware docs: `hardware/`
- Shark-fin antenna design: `hardware/shark_fin_antenna.md`