# Wiring Guide — Terra-Fin Agent

> **Platform:** Raspberry Pi Zero 2 W
> **Sensors:** 6 sensors across I2C, SPI/ADC, and UART

---

## GPIO Header (J8) — Pin Assignments

```
GPIO HEADER (J8):
                    Pi Zero 2 W
 3.3V  (1)  (2)  5V          ← Power for sensors
 GPIO2 (3)  (4)  5V          ← SDA (I2C) — SHT40 + MPU-6050
 GPIO3 (5)  (6)  GND         ← SCL (I2C) — SHT40 + MPU-6050
 GPIO4 (7)  (8)  GPIO14      ← UART TXD — (unused, GPS uses USB)
   GND (9)  (10) GPIO15      ← UART RXD — (unused, GPS uses USB)
GPIO17 (11) (12) GPIO18
GPIO27 (13) (14) GND
GPIO22 (15) (16) GPIO23
   3.3V (17) (18) GPIO24
GPIO10 (19) (20) GND         ← MOSI (SPI) — MCP3008
 GPIO9 (21) (22) GPIO25      ← MISO (SPI) — MCP3008
GPIO11 (23) (24) GPIO8       ← SCLK (SPI) — MCP3008
   GND (25) (26) GPIO7       ← CE0 (SPI) — MCP3008 chip select
   DNC (27) (28) DNC
 GPIO5 (29) (30) GND
 GPIO6 (31) (32) GPIO12
GPIO13 (33) (34) GND
GPIO19 (35) (36) GPIO16
GPIO26 (37) (38) GPIO20
   GND (39) (40) GPIO21
```

## I2C Bus (bus 1)

| Sensor | I2C Address | SDA (pin 3) | SCL (pin 5) | VCC | GND |
|--------|-----------|-------------|-------------|-----|-----|
| SHT40 (temp/humidity) | 0x44 | GPIO2 | GPIO3 | 3.3V | GND |
| MPU-6050 (IMU) | 0x68 | GPIO2 | GPIO3 | 3.3V | GND |

Both I2C sensors share the same SDA/SCL bus. Wire them in parallel.

## SPI Bus → MCP3008 ADC

| MCP3008 Pin | Pi Pin | SPI Function |
|-------------|--------|-------------|
| VDD | 3.3V (pin 1) | Power |
| VREF | 3.3V (pin 1) | Reference voltage |
| AGND | GND (pin 6) | Analog ground |
| CLK | GPIO11 (pin 23) | SCLK |
| DOUT | GPIO9 (pin 21) | MISO |
| DIN | GPIO10 (pin 19) | MOSI |
| CS/SHDN | GPIO8 (pin 24) | CE0 |
| DGND | GND (pin 6) | Digital ground |

### MCP3008 Analog Channels

| Channel | Sensor | Input Range |
|---------|--------|-------------|
| CH0 | Capacitive Soil Moisture | 0-3.3V → 0-100% |
| CH1 | pH Sensor | 0-3.3V → pH 0-14 |
| CH2 | LDR Light Sensor | 0-3.3V → 0-100,000 lux |
| CH3-7 | Unused (available for expansion) | — |

## UART — GPS

GPS module (u-blox NEO-M8N) connects via **USB UART adapter** (not GPIO UART):
- Plug GPS USB adapter into Pi Zero 2 W micro-USB port (via OTG cable)
- Appears as `/dev/ttyACM0`
- Baud rate: 9600 (default), can increase to 38400 for faster fixes

## Power

| Component | Power Source | Notes |
|-----------|-------------|-------|
| Pi Zero 2 W | 5V via micro-USB (power bank) | ~100-200 mA idle, ~350 mA with sensors |
| SHT40 | 3.3V from Pi header | 0.2 mA active |
| MPU-6050 | 3.3V from Pi header | 3.9 mA active |
| MCP3008 | 3.3V from Pi header | 0.5 mA active |
| Soil moisture | 3.3V from Pi header | 5 mA active |
| pH sensor | 3.3V from Pi header | 5-10 mA active |
| GPS | 3.3V (on module) via USB | 25-67 mA active |

## config.txt Settings

Add to `/boot/config.txt`:

```ini
# Enable I2C
dtparam=i2c_arm=on

# Enable SPI
dtparam=spi=on

# Enable UART (for USB-serial GPS)
enable_uart=1

# Disable Bluetooth to free UART (optional)
# dtoverlay=disable-bt
```

## Verification Commands

```bash
# Check I2C devices
sudo i2cdetect -y 1
# Should show: 0x44 (SHT40) and 0x68 (MPU-6050)

# Check SPI
ls -la /dev/spidev0.*
# Should show: /dev/spidev0.0 /dev/spidev0.1

# Check GPS
ls /dev/ttyACM*
# Should show: /dev/ttyACM0

# Test GPS
cgps -s /dev/ttyACM0

# Read ADC (quick test)
python3 -c "
import spidev
spi = spidev.SpiDev()
spi.open(0, 0)
r = spi.xfer2([1, (8)<<4, 0])
print(f'CH0 raw: {((r[1]&3)<<8)+r[2]}')
spi.close()
"
```

## First-Time Checklist

1. [ ] Flash Pi OS Lite (64-bit) to SD card
2. [ ] Enable SSH (add `ssh` file to boot partition)
3. [ ] Configure WiFi (add `wpa_supplicant.conf` to boot partition)
4. [ ] Boot Pi, SSH in
5. [ ] `sudo raspi-config` → Interface Options → enable I2C, SPI
6. [ ] Edit `/boot/config.txt` with settings above
7. [ ] Reboot
8. [ ] Verify I2C: `sudo i2cdetect -y 1`
9. [ ] Verify SPI: `ls /dev/spidev0.*`
10. [ ] Verify GPS: `ls /dev/ttyACM0`
11. [ ] Install Python deps: `pip install pyyaml`
12. [ ] Clone project: `git clone <repo> ~/terra-fin`
13. [ ] Run mock test: `cd ~/terra-fin && python -m pytest tests/ -v`
14. [ ] Run agent: `python -m src.main --mock`