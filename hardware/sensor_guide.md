# Sensor Placement Guide — Terra-Fin Walking Stick

> **Goal:** Sensors positioned for accurate readings while keeping the
> stick lightweight and balanced for walking.

---

## Stick Layout (top to bottom)

```
    [SHARK FIN] — cellular + GNSS antennas (top of stick)
       |          3D-printed PETG, 60x25x35mm
       |          U.FL pigtails run down through shaft
    [HANDLE] — grip area (no electronics)
       |
    [GPS ANTENNA] — upper third, faces sky
       |          (only if using separate NEO-M8N, not SIM7600 GNSS)
       |
    [PROJECT BOX] — Pi Zero 2 W + power bank + ADC
       |            mounted on shaft with velcro
    [I2C SENSORS] — SHT40 + MPU-6050
       |              in the project box or just below
       |
    [MID SHAFT] — clean grip area for walking
       |
       |
    [PROBE TIP] — soil moisture + pH sensors
       |          detachable, 10-15 cm insertion
    [POINT] — metal tip for ground penetration
```

## Sensor Placement Details

### GPS Module (NEO-M8N)
- **Position:** Upper third of stick, antenna facing sky
- **Why:** GPS patch antenna needs clear sky view. Mounting on the
  shaft (not the tip) keeps it above ground and away from the farmer's body.
- **Mounting:** Small project box velcro'd to shaft, USB cable running inside
  or along the shaft to the Pi.
- **Cable:** USB OTG cable from GPS to Pi micro-USB port.
- **Note:** If using the SIM7600G-H cellular modem with its built-in
  GNSS receiver, the NEO-M8N can be omitted. The GNSS patch antenna in
  the shark fin feeds GPS data to the SIM7600, which provides both
  cellular and GPS over a single USB connection.

### Cellular Modem (SIM7600G-H)
- **Position:** Inside the main project box (mid-shaft) alongside the Pi
- **Why:** The modem needs to be near the Pi for USB connection, but the
  antenna is in the shark fin at the top of the stick. U.FL pigtails
  (10-15 cm) connect modem to antenna through the stick shaft.
- **Mounting:** Inside the project box, secured with double-sided tape or
  a 3D-printed bracket. Keep the modem away from the GPS/IMU to minimize
  RF interference.
- **Cable:** USB OTG cable from modem to Pi micro-USB port (second port).
  U.FL pigtails from modem ANT_MAIN to shark-fin cellular antenna, and
  from modem GNSS_ANT to shark-fin GNSS antenna (if using).
- **Power:** 5V USB. If using a dedicated USB port on the power bank
  (recommended), run a separate USB cable.
- **SIM card:** Inserted into the on-module SIM slot before enclosure.

### Shark-Fin Antenna Enclosure
- **Position:** Very top of the stick — the highest point when upright
- **Why:** Maximum sky coverage for cellular towers and GNSS satellites.
  The fin shape is omnidirectional, snag-resistant, and weatherproof.
- **Contents:** Cellular LTE patch antenna (bottom layer) + optional
  GNSS patch antenna (top layer, separated by foam spacer)
- **Cable:** U.FL pigtails route down through the stick shaft (hollow
  stick or drilled channel) to the SIM7600 modem in the project box
- **Mounting:** Threaded cap (recommended), adhesive, or set-screw collar
- **Waterproofing:** IP65 equivalent — silicone-sealed base, weep hole
  for condensation drainage. See `hardware/shark_fin_antenna.md`.

### SHT40 (Temperature/Humidity)
- **Position:** Inside the main project box on the shaft
- **Why:** Ambient air temp/humidity — needs airflow but not direct sun.
  The project box provides shade and some airflow.
- **Notes:** Add a small ventilation hole in the project box for accurate
  humidity readings. Do not seal completely.

### MPU-6050 (IMU)
- **Position:** Inside the main project box, oriented with Z-axis pointing
  up along the stick shaft
- **Why:** Measures stick orientation and motion. Z-axis up means
  gravity reads ~9.81 m/s² on Z when the stick is upright.
- **Notes:** The IMU detects when the stick is moving (walking) vs stationary
  (stuck in ground for night mode). Also detects tilt (leaning against a tree).

### MCP3008 ADC
- **Position:** Inside the main project box
- **Why:** Central hub for all analog sensors. SPI connection to Pi,
  analog channels to soil moisture, pH, and light sensors.
- **Wiring:** 3 analog channels run down the inside of the shaft to the
  probe tip. Use thin jumper wires routed through or along the shaft.

### Capacitive Soil Moisture Sensor
- **Position:** At the very tip of the stick, pointing down
- **Depth:** Insert 10-15 cm into soil for a reading
- **Waterproofing:** The sensor PCB is NOT waterproof. Coat the electronics
  in silicone sealant, leaving only the sensing area exposed. Alternatively,
  mount it in a small waterproof sleeve at the tip.
- **Cable:** Analog wire runs up through the shaft to MCP3008 CH0.

### pH Probe
- **Position:** At the tip, alongside the moisture sensor
- **Depth:** Same 10-15 cm insertion
- **Waterproofing:** pH probes are already waterproof (immersion-designed).
  The connection point between probe and wire needs heat shrink + silicone.
- **Cable:** Analog wire runs up through the shaft to MCP3008 CH1.
- **Maintenance:** pH probes need periodic calibration with buffer solutions
  (pH 4.0 and pH 7.0). Calibrate monthly for accurate readings.

### LDR Light Sensor
- **Position:** On the project box exterior, facing up/forward
- **Why:** Needs to "see" ambient light levels. Don't mount inside the box.
- **Mounting:** Small hole in the project box, LDR protruding slightly,
  sealed with silicone around the edges.
- **Cable:** Analog wire to MCP3008 CH2.

---

## Weight Distribution

|| Position | Component | Weight (g) |
|----------|-----------|-----------|
| Top of stick | Shark-fin enclosure + antennas | ~38 |
| Upper shaft | GPS + box (if separate NEO-M8N) | ~40 |
| Mid shaft | Pi + power bank + ADC + I2C + cellular modem | ~265 |
| Tip | Soil moisture + pH probe | ~25 |
| **Total** | | **~368 g** |

The mid-shaft placement of the power bank (heaviest item) keeps the
center of gravity near the farmer's hand, making the stick easy to carry.
The shark fin at the top adds only 38 g — not enough to make the stick
top-heavy.

## Waterproofing

The stick will be used outdoors and the probe tip goes into soil:

1. **Project box:** Choose IP65 or better, or seal edges with silicone
2. **Probe tip connections:** Heat shrink + silicone on all wire joints
3. **Capacitive moisture sensor:** Coat PCB in silicone, leave sensing area
4. **pH probe:** Factory waterproof, just protect the wire junction
5. **Cable routing:** Run wires through the hollow shaft if possible,
   or tape securely to the exterior with waterproof tape

## Detachable Probe Tip

For travel and maintenance, make the probe tip detachable:

- Use a threaded connector (like a camera tripod quick-release) at the
  midpoint between the shaft and the probe section
- This allows removing the dirty/wet probe for cleaning while keeping
  the electronics dry in the project box
- The analog wires connect via a small 3-pin connector (GND, VCC, signal
  for each sensor — use a 4-pin or 6-pin JST connector)

## Maintenance Schedule

| Task | Frequency |
|------|-----------|
| Clean soil probe tip | After each use |
| Calibrate pH probe | Monthly |
| Check waterproofing | Monthly |
| Replace power bank | Daily (or as needed) |
| Check sensor readings vs known values | Weekly |
| Full system test (pytest) | After any code change |