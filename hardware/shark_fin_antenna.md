# Shark-Fin Antenna Enclosure — Terra-Fin Agent

> **Goal:** House the cellular modem's primary antenna (and optionally a
> GNSS patch antenna) inside a aerodynamic shark-fin-shaped plastic cap
> that mounts on top of the walking stick, maximizing sky coverage and
> protecting the antenna from rain, dust, and branch-snagging.

---

## Why a Shark Fin?

A shark-fin shape is the industry standard for vehicle roof antennas
because it combines three advantages that are equally valuable on a
walking stick:

1. **Omnidirectional radiation pattern** — the curved shape doesn't
   favor any azimuth direction, so the stick works regardless of which
   way the farmer faces.
2. **Sky-facing aperture** — the broad flat underside and gently
   sloping top give the patch antenna a clear hemisphere view of the
   sky for both cellular towers and GNSS satellites.
3. **Snag resistance** — the smooth, swept-back profile won't catch on
   branches when the stick is used to reach fruit or pushed through
   dense foliage.

On a walking stick it also provides a natural grip cap — the farmer can
grab the fin to pull the stick free from soil without touching the dirty
probe tip.

---

## Dimensions

```
         ┌──── apex (15 mm) ────┐
        /                        \
       /                          \  ← swept-back curve
      /                            \
     /                              \
    /  ┌──────────────────────────┐  \
   /   │   antenna cavity          │   \
  └────┴──────────────────────────┴────┘ ← base (60 mm)
  │                                    │
  │           35 mm height             │
  │           60 mm width              │
  │           25 mm depth              │
  └────────────────────────────────────┘
```

| Dimension | Value | Notes |
|-----------|-------|-------|
| Overall height | 35 mm | Low enough not to lever in wind |
| Base width | 60 mm | Spans the 25-30 mm stick shaft + glue margin |
| Base depth | 25 mm | Enough room for modem U.FL pigtail |
| Wall thickness | 2.0 mm | PETG/ABS, IP65 with silicone seal |
| Internal cavity | 56 × 21 × 28 mm | Fits antenna PCB + GNSS patch |
| Apex thickness | 1.5 mm | Thinner at top for RF transparency |
| Weight | ~25 g | Printed PETG + antenna |

---

## Internal Layout

```
           SHARK FIN — cross section (side view)

         ╭─── apex ───╮
        ╱   (solid)    ╲
       ╱                ╲
      ╱  ┌────────────┐  ╲
     ╱   │  air gap   │   ╲
    ╱    │            │    ╲
   ╱     │ ┌────────┐ │     ╲
  ╱      │ │GNSS    │ │      ╲
 ╱       │ │patch  │ │       ╲
╱        │ │(opt)  │ │        ╲
└────────┴─┴────────┴─┴────────┘
│         │ cellular │          │
│         │ patch    │          │
│         │ antenna  │          │
│  U.FL   │          │          │
│ pigtail │          │          │
└─────────┴──────────┴──────────┘
              ↑
         stick shaft (passes through base)
```

### Layer 1 (bottom): Cellular antenna
- **Component:** SIMCom primary cellular antenna (comes with SIM7600 dev kit)
  or a third-party LTE patch antenna (e.g., Taoglas Patch.4G.25)
- **Size:** ~50 × 20 × 3 mm typical
- **Orientation:** Flat side faces up (sky), radiator toward the apex
- **Connector:** U.FL (IPEX) pigtail, ~10 cm, routes down through the
  stick shaft to the modem in the mid-shaft project box

### Layer 2 (top): GNSS patch antenna (optional)
- **Component:** u-blox ANN-MB or similar 25×25×4 mm GNSS patch
- **Size:** 25 × 25 × 4 mm
- **Orientation:** Patch surface faces the apex (sky)
- **Connector:** U.FL pigtail, ~15 cm, routes down to the GPS module
- **Why here:** The SIM7600G-H has a built-in GNSS receiver, so a single
  antenna in the fin can serve both cellular and GPS — eliminating the
  separate GPS box on the upper shaft described in the original design.

### Air gap
- 2-3 mm air gap between the cellular and GNSS antennas prevents
  capacitive coupling and detuning.  A thin foam spacer (closed-cell
  EVA) holds the antennas in position.

---

## 3D Printing

### Material
**PETG** (recommended) or **ABS**
- PETG: Easier to print, good layer adhesion, food-safe, UV-stable
  with additives.  Slightly flexible — good for impact resistance.
- ABS: More rigid, better heat resistance (Kenyan sun can heat dark
  surfaces to 60°C+).  Harder to print without enclosure.

**Avoid PLA** — it softens at 50-55°C and will deform in direct sun.

### Print Settings
| Setting | Value |
|---------|-------|
| Layer height | 0.2 mm |
| Wall thickness | 2.0 mm (4 perimeters) |
| Infill | 20% gyroid |
| Top layers | 4 (for RF transparency, keep solid but thin) |
| Bottom layers | 0 (open base mounts on stick) |
| Support | None (designed to be support-free) |
| Print orientation | Base down, apex up |

### Post-Processing
1. Sand the base flat (it mates with the stick shaft)
2. Drill a 5 mm hole in the center of the base for the U.FL pigtails
3. Apply 2 coats of UV-resistant clear coat (e.g., Rust-Oleum UV Clear)
4. Test-fit on the stick — should friction-fit or glue on

### Files
The fin is designed as a simple swept loft that can be generated in
FreeCAD, Fusion 360, or OpenSCAD.  A parametric OpenSCAD model lets you
adjust the fin height, base width, and sweep angle without a full CAD
tool.  See `hardware/scad/shark_fin.scad` (to be created).

---

## Mounting to the Stick

### Option A: Threaded cap (recommended)
- Thread the base of the fin (internal M22 or custom thread)
- Thread the top of the stick shaft to match
- Screw the fin on like a camera tripod cap
- **Pro:** Removable for service; self-centering
- **Con:** Requires threading the stick (lathe or tap-and-die)

### Option B: Adhesive mount (simplest)
- Sand the stick top flat
- Apply marine-grade epoxy (e.g., J-B Weld MarineWeld) to the fin base
- Press on and let cure 24 hours
- **Pro:** No tools, waterproof, permanent
- **Con:** Can't remove without cutting

### Option C: Set-screw collar (field-serviceable)
- Print a collar below the fin that slips over the stick
- 2× M3 set screws clamp the collar to the shaft
- **Pro:** Adjustable height, removable with an Allen key
- **Con:** Screws can back out from vibration; needs thread-lock

### Cable routing
The U.FL pigtails exit the base of the fin and enter the stick shaft:
- **Hollow stick (bamboo):** Route inside the shaft — cleanest
- **Solid stick (hardwood):** Drill a 5 mm channel down the center of
  the top 20 cm, route pigtails inside, seal the entry with silicone

---

## Antenna Selection Guide

### Cellular Antenna
| Spec | Requirement | Notes |
|------|-------------|-------|
| Frequency | 700-2600 MHz | Covers B1/B3/B7/B20/B28 (Safaricom/Airtel Kenya) |
| Type | Patch or PCB | Patch is directional (sky-facing); PCB dipole is omni but taller |
| Gain | 2-5 dBi | Higher gain = narrower beam; 3 dBi is a good balance |
| VSWR | < 2.0:1 | Across all target bands |
| Connector | U.FL (IPEX) | Matches SIM7600 module |
| Size | ≤ 55×25×4 mm | Must fit in the fin cavity |

**Recommended parts:**
- Taoglas Frost.4G.25 (IPXtreme series) — $8-12
- SIMCom bundled antenna (comes with SIM7600 dev board) — $0 (included)
- Molex 2065130001 — $5-8

### GNSS Patch Antenna (optional, if using SIM7600 GNSS)
| Spec | Requirement | Notes |
|------|-------------|-------|
| Frequency | 1575.42 MHz (GPS L1) | Also 1602 MHz (GLONASS) if multi-constellation |
| Gain | 28 dB | With built-in LNA |
| Type | Active patch | Needs 3.3V bias via the U.FL line |
| Connector | U.FL (IPEX) | |
| Size | 25×25× 4 mm | Standard ceramic patch |

**Recommended parts:**
- u-blox ANN-MB-00 — $10-15
- Taoglas.2547B.A.GAAA — $6-10
- Generic active GPS patch (AliExpress) — $2-4

---

## Waterproofing

The fin sits on top of the stick in all weather.  Sealing strategy:

1. **Print material:** PETG is inherently water-resistant; ABS is
   slightly porous — seal with clear coat
2. **Base joint:** Silicone gasket between fin base and stick shaft
   (cut from 1 mm silicone sheet, or apply silicone sealant ring)
3. **Cable entry:** U.FL pigtails enter through a single 5 mm hole;
   seal with a dab of marine silicone after routing
4. **Drainage:** A 1 mm weep hole at the lowest point of the internal
   cavity lets condensation drain, not pool
5. **Ventilation:** Not needed — the fin is a sealed cavity, not a
   vented enclosure.  The weep hole handles moisture.

**Target:** IP65 equivalent (rainproof, dust-tight, not submersible).

---

## RF Performance Notes

### Placement on the stick
The fin is at the **top** of the stick — the highest point when
upright.  This gives:
- Best line-of-sight to cellular towers (over the farmer's head)
- Best GNSS satellite visibility (full sky hemisphere)
- Maximum separation from the Pi Zero's switching noise (~1-1.5 m
  from the mid-shaft project box)

### Body absorption
The farmer's hand and body are below the fin when walking, so the
fin is above the body shadow — good for both cellular and GNSS.
When the stick is stuck in the ground for night mode, the fin is
fully exposed with no body obstruction.

### Ground plane
A patch antenna needs a ground plane below it for proper operation.
The aluminum or copper tape on the inside of the fin base serves
as the ground plane:
- Cut a 50×25 mm piece of copper tape (or aluminum foil)
- Apply to the inside of the fin base, under the cellular antenna
- This improves gain by 2-3 dB and flattens the radiation pattern

### Cable loss
U.FL pigtails have ~0.5 dB loss per 10 cm at 2 GHz.  Keeping the
pigtail short (10-15 cm) keeps total loss under 1 dB.  Do not coil
excess cable — cut to length or route in a gentle S-curve.

---

## Weight & Balance Impact

| Component | Weight (g) |
|-----------|-----------|
| 3D-printed PETG fin | 18 |
| Cellular patch antenna | 5 |
| GNSS patch antenna (opt) | 8 |
| U.FL pigtails (2×) | 3 |
| Copper ground plane tape | 2 |
| Silicone sealant | 2 |
| **Total** | **~38 g** (without GNSS: ~30 g) |

The fin is at the top of the stick, so 38 g at ~130 cm from the
pivot point adds a small top-weight.  The power bank (180 g) at
mid-shaft still dominates the center of gravity, so balance is
maintained.  The fin is light enough that the farmer won't notice
it while walking.

### Updated total weight (with shark fin)

| Component | Weight (g) |
|-----------|-----------|
| Stick (wood, 130 cm) | 500 |
| Pi Zero 2 W + SD card | 10 |
| Power bank (10,000 mAh) | 180 |
| GPS module (if not using SIM7600 GNSS) | 10 |
| Cellular modem (SIM7600) | 25 |
| Sensors (SHT40, MPU-6050, MCP3008) | 15 |
| Soil moisture + pH probe | 25 |
| Wiring + connectors | 20 |
| Project boxes (mid-shaft) | 40 |
| Shark-fin antenna enclosure | 38 |
| Mounting hardware | 15 |
| **Total** | **~878 g** |

Still under 1 kg electronics + stick.  With the stick (~500 g) the
total is ~1.4 kg — the same as before the fin was added.

---

## Assembly Checklist

1. [ ] 3D-print the fin shell (PETG, 0.2 mm layer height)
2. [ ] Sand base flat, drill 5 mm cable hole
3. [ ] Apply copper ground plane tape inside base
4. [ ] Solder U.FL pigtail to cellular antenna (or use pre-assembled)
5. [ ] Solder U.FL pigtail to GNSS antenna (if using)
6. [ ] Place cellular antenna on ground plane, patch face up
7. [ ] Place foam spacer on cellular antenna
8. [ ] Place GNSS patch on spacer, face up
9. [ ] Route both U.FL pigtails through the 5 mm hole
10. [ ] Apply silicone sealant around cable entry
11. [ ] Apply UV clear coat (2 coats, 4 hours between)
12. [ ] Install weep hole at lowest cavity point (1 mm drill)
13. [ ] Mount fin on stick (threaded / adhesive / set-screw)
14. [ ] Route U.FL pigtails down to modem (inside shaft or channel)
15. [ ] Connect U.FL to modem primary antenna port
16. [ ] Connect GNSS U.FL to SIM7600 GNSS port (if using)
17. [ ] Verify: `AT+CSQ` returns valid RSSI; `AT+CGNSSINFO` returns fix
18. [ ] Seal base joint with silicone gasket or sealant
19. [ ] Water test: spray with hose for 5 min, check interior is dry

---

## Cost Summary

| Component | Budget Price | Recommended Price |
|-----------|-------------|-------------------|
| 3D-printed PETG fin | $1 (filament) | $3 (commercial print) |
| Cellular patch antenna | $2 (generic) | $10 (Taoglas) |
| GNSS patch antenna (opt) | $2 (generic) | $12 (u-blox ANN-MB) |
| U.FL pigtails (2×) | $1 | $3 |
| Copper tape | $1 | $2 |
| Silicone sealant | $1 | $3 |
| UV clear coat | $2 | $5 |
| **Total (with GNSS)** | **$10** | **$38** |
| **Total (cellular only)** | **$8** | **$26** |

---

## Integration with Existing Design

This shark fin replaces the "GPS box (upper shaft)" described in
`stick_design.md` and `sensor_guide.md`.  When using the SIM7600G-H's
built-in GNSS receiver, the separate NEO-M8N GPS module is no longer
needed — the GNSS antenna in the fin feeds the SIM7600, which provides
both cellular and GPS over a single USB connection.

If keeping the NEO-M8N as a dedicated GPS (redundancy or power
savings), the fin's GNSS antenna can be omitted, and the NEO-M8N
remains in its upper-shaft box as before.  The fin then houses only
the cellular antenna, reducing its internal complexity.

### SIM7600G-H Pinout Summary (USB connection to Pi Zero)

| Function | SIM7600 Pin | Pi Zero Connection |
|----------|-------------|-------------------|
| USB D+ | USB | micro-USB via OTG |
| USB D- | USB | micro-USB via OTG |
| Power | VBAT (3.7-4.2V) or USB 5V | USB 5V or LiPo |
| Cellular antenna | ANT_MAIN | U.FL → shark fin |
| GNSS antenna | GNSS_ANT | U.FL → shark fin (opt) |
| SIM card | On-module SIM slot | Insert SIM |
| Reset | RST | GPIO (optional) |
| PWR_KEY | PWR | GPIO (optional, for power control) |

The SIM7600 appears as multiple `/dev/ttyUSB*` devices:
- `/dev/ttyUSB0` — diagnostic
- `/dev/ttyUSB1` — GPS NMEA data
- `/dev/ttyUSB2` — AT command data port (primary)
- `/dev/ttyUSB3` — audio (unused)

The cellular sensor driver reads from `/dev/ttyUSB2` by default
(configurable via `CellularConfig.port`).