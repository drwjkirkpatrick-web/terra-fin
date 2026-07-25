# Parts List — Terra-Fin Agent

> **Target:** Raspberry Pi Zero 2 W on a walking stick
> **Goal:** Lightweight enough for a full day in the orchard (< 1 kg electronics)
> **Environment:** Kenyan highlands — avocado, orange, and greens harvests

---

## Core Compute

| Component | Model/Part # | Qty | Budget Price | Rec Price | Purpose |
|-----------|-------------|-----|-------------|-----------|---------|
| Pi | Raspberry Pi Zero 2 W | 1 | $15 | $15 | Main compute (1 GHz quad-core, 512 MB RAM) |
| SD Card | 32 GB Class 10 | 1 | $6 | $8 | OS + data storage |
| Power Bank | 10,000 mAh USB | 1 | $8 | $15 | All-day power (~25-40 hrs) |
| USB cable | Short micro-USB | 1 | $2 | $3 | Power bank to Pi |

## Sensors

|| Component | Model/Part # | Qty | Budget Price | Rec Price | Interface | Purpose |
|-----------|-------------|-----|-------------|-----------|-----------|---------|
| Soil Moisture | Capacitive Soil Moisture Sensor v1.2 | 1 | $3 | $5 | ADC (MCP3008 ch 0) | Ground moisture at stick tip |
| Soil pH | Analog pH Sensor Kit (Atlas Scientific) | 1 | $40 | $85 | ADC (MCP3008 ch 1) | Soil pH at stick tip |
| GPS | u-blox NEO-M8N | 1 | $8 | $25 | USB UART | Location tracking |
| Temp/Humidity | SHT40 Breakout | 1 | $5 | $13 | I2C 0x44 | Ambient conditions |
| Light | LDR (GL5528) + resistor | 1 | $1 | $2 | ADC (MCP3008 ch 2) | Day/night detection |
| IMU | MPU-6050 breakout | 1 | $3 | $5 | I2C 0x68 | Motion / orientation |
| ADC | MCP3008 | 1 | $3 | $5 | SPI | Analog-to-digital for moisture/pH/light |
| **Cellular Modem** | **SIMCom SIM7600G-H** | **1** | **$15** | **$30** | **USB UART** | **4G LTE modem for telemetry upload** |
| **Cellular Antenna** | **LTE patch (Taoglas or generic)** | **1** | **$2** | **$10** | **U.FL → fin** | **Primary cellular antenna in shark fin** |
| **GNSS Patch (opt)** | **u-blox ANN-MB or generic** | **1** | **$2** | **$12** | **U.FL → fin** | **GNSS antenna in shark fin (if using SIM7600 GNSS)** |

> **Note:** If using the SIM7600G-H's built-in GNSS receiver, the separate
> NEO-M8N GPS module above can be omitted. The GNSS patch antenna in the
> shark fin then feeds both cellular and GPS through the single SIM7600
> USB connection. See `hardware/shark_fin_antenna.md` for details.

## Power & Wiring

| Component | Model/Part # | Qty | Budget Price | Purpose |
|-----------|-------------|-----|-------------|---------|
| Jumper wires | Female-to-female 20cm | 20 | $2 | Pi to sensor connections |
| Protoboard | Half-size | 1 | $2 | ADC + wiring hub |
| Heat shrink | Assorted | 1 | $2 | Waterproofing probe connections |
| Silicone sealant | Small tube | 1 | $3 | Waterproofing probe tip |

## Enclosure & Mounting

| Component | Model/Part # | Qty | Budget Price | Purpose |
|-----------|-------------|-----|-------------|---------|
| Project box | 60x40x20mm | 1 | $2 | Pi + sensor housing on stick shaft |
| Velcro strips | Adhesive | 1 | $2 | Detachable mount on stick |
| Cable ties | Small assortment | 10 | $1 | Cable management |
| Stick | Wooden walking stick | 1 | $5 | The stick itself (local) |

---

## Total Weight Estimate

|| Item | Weight (g) |
|------|-----------|
| Pi Zero 2 W | 8 |
| SD card | 2 |
| Power bank (10,000 mAh) | 180 |
| All sensors + ADC | 35 |
| Cellular modem (SIM7600) | 25 |
| Shark-fin enclosure + antennas | 38 |
| Wiring + protoboard | 20 |
| Enclosure | 25 |
| **Total electronics** | **~333 g** |

Well under the 1 kg target. The walking stick itself (wood, ~400-600 g)
brings the total to under 1 kg.

## Total Cost Estimate

|| Tier | Total |
|------|-------|
| Budget (all budget parts, with cellular) | ~$109 |
| Recommended (all rec parts, with cellular) | ~$243 |
| Budget (cellular only, no separate GPS) | ~$101 |
| Recommended (cellular only, no separate GPS) | ~$230 |

## Notes

- **Power bank selection:** A 10,000 mAh bank gives ~25-40 hours depending on
  polling interval. For multi-day trips, consider a 20,000 mAh bank ($20-30).
- **GPS antenna:** Must face sky. Mount on the upper portion of the stick
  shaft, not the tip (which goes into soil).
- **Soil probe depth:** The capacitive moisture sensor and pH probe are at the
  tip of the stick. Insert 10-15 cm into the soil for a reading.
- **Budget vs recommended:** The main quality differences are in the GPS module
  (NEO-M8N vs cheaper NEO-6M) and the pH sensor (Atlas Scientific vs generic).
  Budget parts work but may be less accurate or durable.
- **Local sourcing:** In Kenya, many parts are available from:
  - Nailab / iLab (Nairobi) for Pi and basic sensors
  - Jumia Kenya for power banks and accessories
  - Direct import from AliExpress for budget sensors (2-4 week delivery)