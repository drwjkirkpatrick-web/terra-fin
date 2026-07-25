# Walking Stick Design Notes

> **Goal:** A practical walking stick that carries an agricultural sensor
> agent while remaining lightweight and comfortable for a full day in
> the orchard.

---

## Stick Material

**Recommended:** Hardwood (oak, ash, or local Kenyan hardwood)
- Diameter: 25-30 mm (1 inch)
- Length: 120-140 cm (adjust to farmer height)
- Weight: 400-600 g (stick only)
- Why: Durable, comfortable grip, naturally weather-resistant. Can be
  carved or sourced locally.

**Alternative:** Bamboo
- Lighter (~200-300 g)
- Hollow center allows internal cable routing
- Less durable for ground penetration (needs metal tip)

## Electronic Housing

**Main project box** (mid-shaft):
- Size: 60 x 40 x 20 mm (Pi Zero 2 W + MCP3008 + I2C sensors)
- Material: ABS plastic or 3D-printed PETG
- Mounting: Velcro straps around the stick shaft
- Access: Hinged or screw-on lid for battery/sensor access
- Ventilation: One 2mm hole for SHT40 humidity readings

**Power bank mount** (just below or beside project box):
- Size: Fits 10,000 mAh power bank (~70 x 35 x 20 mm)
- Mounting: Velcro strap or dedicated pocket
- Access: Removable for daily charging

**GPS box** (upper shaft):
- Size: 30 x 20 x 15 mm (just the GPS module)
- Mounting: Velcro, antenna facing up
- Position: Upper third of stick for sky visibility
- **Note:** When using the SIM7600 cellular modem with its built-in
  GNSS receiver, this separate GPS box is replaced by the shark-fin
  antenna enclosure on top of the stick (see below). The SIM7600
  provides both cellular and GPS over a single USB connection, and
  its GNSS patch antenna lives inside the shark fin.

**Shark-fin antenna enclosure** (top of stick):
- Size: 60 x 25 x 35 mm (fin shape, 3D-printed PETG)
- Mounting: Threaded cap, adhesive, or set-screw collar on stick top
- Position: Very top of stick — highest point for maximum sky coverage
- Contents: Cellular LTE patch antenna + optional GNSS patch antenna
- Cable: U.FL pigtails route down through the stick shaft to the
  SIM7600 modem in the mid-shaft project box
- See `hardware/shark_fin_antenna.md` for full design details

## Probe Tip Design

The bottom 20 cm of the stick is a detachable probe section:

```
    ───────────  ← Detachable connector (threaded or quick-release)
    |  Wires   | ← 3-pin connector for sensor signals
    |  pass    | ← runs through this section
    |  through |
    ───────────
    |  Soil    | ← Capacitive moisture sensor
    |  moisture|   (flat PCB, facing outward)
    ───────────
    |  pH      | ← pH probe (cylinder, ~5mm diameter)
    |  probe   |   (alongside moisture sensor)
    ───────────
    |  Metal   | ← Pointed tip for ground penetration
    |  point   |   (stainless steel, protects sensors)
    ───────────
```

## Cable Routing

**Option A: External (simpler)**
- Tape wires to the outside of the stick with waterproof tape
- Pros: Easy to build, easy to repair
- Cons: Less clean, wires can snag

**Option B: Internal (if hollow stick)**
- Route wires through the hollow center of the stick
- Pros: Clean, protected
- Cons: Harder to build, harder to repair

**Option C: Channel (compromise)**
- Carve or drill a shallow channel along the stick
- Press wires into channel and seal with tape or epoxy
- Pros: Clean look, protected, moderate difficulty

## Weight Budget

|| Component | Weight (g) |
|-----------|-----------|
| Wooden stick (130 cm) | 500 |
| Pi Zero 2 W + SD card | 10 |
| Power bank (10,000 mAh) | 180 |
| GPS module (if separate NEO-M8N) | 10 |
| Cellular modem (SIM7600) | 25 |
| Sensors (SHT40, MPU-6050, MCP3008) | 15 |
| Soil moisture + pH probe | 25 |
| Wiring + connectors | 20 |
| Project boxes (2) | 40 |
| Shark-fin antenna enclosure | 38 |
| Mounting hardware | 15 |
| **Total** | **~878 g** |

Well under 1 kg. A typical wooden walking stick weighs 400-600 g,
so the total weight (1.3-1.5 kg) is reasonable for a day in the orchard.

## Balance

- **Center of gravity:** Should be at the hand grip (mid-upper stick)
- **Power bank:** Heaviest single item — mount at hand grip level
- **Probe tip:** Lightweight sensors only — won't make the stick top-heavy
- **GPS:** Very light — negligible effect on balance

## Farmer Experience

The stick should feel like a normal walking stick with a slightly thicker
grip area (where the project box is). Key design considerations:

1. **Grip area must be clean** — no wires, tape, or boxes where the hand goes
2. **Probe tip must be robust** — it will be thrust into soil repeatedly
3. **Power bank must be easily removable** — charged every night
4. **GPS antenna must face sky** — when stick is upright
5. **Sensors must be accessible** — for cleaning and calibration
6. **The stick must still work as a stick** — for walking support and
   reaching fruit on branches

## Night Mode Placement

When the stick is stuck in the ground for night mode:
- The stick stands upright, probe in soil
- GPS antenna faces sky (good for position logging)
- IMU detects any motion/vibration (good for intruder detection)
- Light sensor confirms darkness
- The project box and power bank are at comfortable height, not on the ground

The stick naturally becomes a sentinel when placed upright in the soil.