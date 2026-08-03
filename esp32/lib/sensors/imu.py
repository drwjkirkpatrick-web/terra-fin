"""MPU-6050 IMU driver for ESP32.

Uses ESP32 I2C. Reads accelerometer and gyroscope registers directly.
"""

import logging
import struct
import time
from core.sensor_base import SensorBase
from core.types import SensorReading, utc_now
from core.mock_manager import MockManager
from core.config import IMUConfig

logger = logging.getLogger(__name__)

_MPU6050_ADDR = 0x68
_PWR_MGMT_1 = 0x6B
_ACCEL_XOUT_H = 0x3B
_MPU_SCALE = 16384.0
_GYRO_SCALE = 131.0

try:
    from machine import I2C, Pin
    _HAS_MACHINE = True
except ImportError:
    _HAS_MACHINE = False


class IMUSensor(SensorBase):
    name = "imu"
    metrics = ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"]
    bus_type = "i2c"
    description = "MPU-6050 on ESP32 I2C"

    def __init__(self, config=None, mock_mode=False):
        if config is None:
            config = IMUConfig()
        super().__init__(config=config, mock_mode=mock_mode or config.mock_mode)
        self._mock = MockManager()
        self._i2c = None
        self._addr = config.i2c_address if config else _MPU6050_ADDR

    def _init_hardware(self):
        if not _HAS_MACHINE:
            return False
        try:
            scl = self._config.scl_pin if self._config else 22
            sda = self._config.sda_pin if self._config else 21
            self._i2c = I2C(self._config.i2c_id if self._config else 0,
                           scl=Pin(scl), sda=Pin(sda),
                           freq=self._config.i2c_freq if self._config else 100000)
            devices = self._i2c.scan()
            if self._addr not in devices:
                return False
            self._i2c.writeto_mem(self._addr, _PWR_MGMT_1, bytes([0x00]))
            time.sleep_ms(10)
            logger.info("[imu] MPU-6050 ready on I2C 0x%02X", self._addr)
            return True
        except Exception as e:
            logger.error("[imu] I2C init failed: %s", e)
            return False

    def _read_hardware(self):
        if self._i2c is None:
            return None
        try:
            data = self._i2c.readfrom_mem(self._addr, _ACCEL_XOUT_H, 14)
            if len(data) != 14:
                return None
            ax, ay, az, temp, gx, gy, gz = struct.unpack(">7h", data)
            return SensorReading(
                sensor_name=self.name,
                timestamp=utc_now(),
                metrics={
                    "accel_x": round(ax / _MPU_SCALE, 3),
                    "accel_y": round(ay / _MPU_SCALE, 3),
                    "accel_z": round(az / _MPU_SCALE, 3),
                    "gyro_x": round(gx / _GYRO_SCALE, 3),
                    "gyro_y": round(gy / _GYRO_SCALE, 3),
                    "gyro_z": round(gz / _GYRO_SCALE, 3),
                },
                units={
                    "accel_x": "g", "accel_y": "g", "accel_z": "g",
                    "gyro_x": "deg/s", "gyro_y": "deg/s", "gyro_z": "deg/s",
                },
                metadata={},
            )
        except Exception as e:
            logger.error("[imu] read failed: %s", e)
            return None

    def _read_mock(self):
        ax, ay, az = self._mock.imu_accel()
        gx, gy, gz = self._mock.imu_gyro()
        return SensorReading(
            sensor_name=self.name,
            timestamp=utc_now(),
            metrics={
                "accel_x": ax, "accel_y": ay, "accel_z": az,
                "gyro_x": gx, "gyro_y": gy, "gyro_z": gz,
            },
            units={
                "accel_x": "g", "accel_y": "g", "accel_z": "g",
                "gyro_x": "deg/s", "gyro_y": "deg/s", "gyro_z": "deg/s",
            },
            metadata={"mock": True},
        )

    def cleanup(self):
        self._i2c = None
