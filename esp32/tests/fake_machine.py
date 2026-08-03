"""Fake machine module for testing ESP32 code on CPython.

Provides mock implementations of MicroPython's machine module:
- Pin, ADC, I2C, SoftI2C, UART, Timer
"""

class Pin:
    IN = 0
    OUT = 1
    PULL_UP = 2
    PULL_DOWN = 3

    def __init__(self, id, mode=-1, pull=-1, value=None):
        self._id = id
        self._mode = mode
        self._pull = pull
        self._value = value if value is not None else 0

    def value(self, v=None):
        if v is not None:
            self._value = v
        return self._value

    def on(self):
        self._value = 1

    def off(self):
        self._value = 0


class ADC:
    ATTN_11DB = 3  # full 0-3.3V range on ESP32
    WIDTH_12BIT = 3

    def __init__(self, pin):
        self._pin = pin
        self._attn = self.ATTN_11DB
        self._width = self.WIDTH_12BIT

    def atten(self, v):
        self._attn = v

    def width(self, v):
        self._width = v

    def read(self):
        # Return a mock value (mid-range)
        return 2048

    def read_uv(self):
        return 1650000  # ~1.65V


class I2C:
    def __init__(self, id, scl=None, sda=None, freq=100000):
        self._id = id
        self._scl = scl
        self._sda = sda
        self._freq = freq
        self._devices = set()

    def scan(self):
        return list(self._devices)

    def readfrom_mem(self, addr, memaddr, nbytes, addrsize=8):
        return bytes(nbytes)

    def writeto_mem(self, addr, memaddr, buf, addrsize=8):
        pass

    def readfrom(self, addr, nbytes, stop=True):
        return bytes(nbytes)

    def writeto(self, addr, buf, stop=True):
        pass


class SoftI2C(I2C):
    pass


class UART:
    def __init__(self, id, baudrate=9600, bits=8, parity=None, stop=1, tx=None, rx=None):
        self._id = id
        self._baudrate = baudrate
        self._bits = bits
        self._parity = parity
        self._stop = stop
        self._tx = tx
        self._rx = rx
        self._buf = b''

    def init(self, baudrate=None, bits=None, parity=None, stop=None):
        if baudrate is not None:
            self._baudrate = baudrate

    def read(self, nbytes=None):
        if nbytes is None:
            r = self._buf
            self._buf = b''
            return r
        r = self._buf[:nbytes]
        self._buf = self._buf[nbytes:]
        return r if r else None

    def readline(self):
        idx = self._buf.find(b'\n')
        if idx < 0:
            return None
        r = self._buf[:idx+1]
        self._buf = self._buf[idx+1:]
        return r

    def write(self, buf):
        return len(buf)

    def any(self):
        return len(self._buf)

    def _feed(self, data):
        self._buf += data.encode() if isinstance(data, str) else data


class Timer:
    PERIODIC = 1
    ONE_SHOT = 0

    def __init__(self, id):
        self._id = id
        self._callback = None

    def init(self, period, mode=None, callback=None):
        self._period = period
        self._mode = mode
        self._callback = callback

    def deinit(self):
        self._callback = None


class PWM:
    def __init__(self, pin):
        self._pin = pin
        self._freq = 1000
        self._duty = 0

    def freq(self, v=None):
        if v is not None:
            self._freq = v
        return self._freq

    def duty_u16(self, v=None):
        if v is not None:
            self._duty = v
        return self._duty

    def deinit(self):
        pass


def unique_id():
    return b'\x00\x00\x00\x00\x00\x00\x00\x00'


def reset():
    pass


def soft_reset():
    pass


def freq():
    return 240000000
