from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from config import SETTINGS, Settings
from core.processing import SensorSample


class SensorReadError(RuntimeError):
    pass


class SupportsRead(Protocol):
    def read(self) -> SensorSample:
        ...

    def close(self) -> None:
        ...


class SimulatedSensorReader:
    def __init__(self, fault_after_samples: int = 0, random_seed: Optional[int] = 7) -> None:
        self.sample_index = 0
        self.fault_after_samples = fault_after_samples
        self.random = random.Random(random_seed)

    def read(self) -> SensorSample:
        self.sample_index += 1
        t = self.sample_index / 100.0
        healthy = self.fault_after_samples <= 0 or self.sample_index < self.fault_after_samples

        vibration_scale = 0.08 if healthy else 0.45
        current_offset = 0.0 if healthy else 1.5
        temperature_offset = 0.0 if healthy else 8.0

        vib_x = math.sin(2 * math.pi * 8 * t) + self.random.gauss(0, vibration_scale)
        vib_y = math.sin(2 * math.pi * 8 * t + 0.3) + self.random.gauss(0, vibration_scale)
        vib_z = math.sin(2 * math.pi * 8 * t + 0.6) + self.random.gauss(0, vibration_scale)
        current = 10.0 + 0.2 * math.sin(2 * math.pi * 2 * t) + current_offset + self.random.gauss(0, 0.05)
        temperature = 45.0 + 0.03 * self.sample_index + temperature_offset + self.random.gauss(0, 0.08)

        return SensorSample(
            timestamp=datetime.now(timezone.utc).isoformat(),
            vib_x=vib_x,
            vib_y=vib_y,
            vib_z=vib_z,
            current=current,
            temperature=temperature,
        )

    def close(self) -> None:
        return None


class I2CBus:
    def __init__(self, bus_id: int) -> None:
        try:
            from smbus2 import SMBus
        except ModuleNotFoundError as exc:
            raise SensorReadError(
                "smbus2 is required for SENSOR_MODE=real. Install requirements first."
            ) from exc

        self.bus_id = bus_id
        try:
            self._bus = SMBus(bus_id)
        except OSError as exc:
            raise SensorReadError(
                f"Unable to open /dev/i2c-{self.bus_id}: {exc}. "
                "Enable I2C on the Pi and verify the bus number."
            ) from exc

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        try:
            return self._bus.read_i2c_block_data(address, register, length)
        except OSError as exc:
            raise SensorReadError(
                "I2C read failed on "
                f"/dev/i2c-{self.bus_id} device=0x{address:02X} register=0x{register:02X} "
                f"length={length}: {exc}. Check sensor power, wiring, and configured address."
            ) from exc

    def read_word_data(self, address: int, register: int) -> int:
        try:
            return self._bus.read_word_data(address, register)
        except OSError as exc:
            raise SensorReadError(
                "I2C read failed on "
                f"/dev/i2c-{self.bus_id} device=0x{address:02X} register=0x{register:02X}: "
                f"{exc}. Check sensor power, wiring, and configured address."
            ) from exc

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        try:
            self._bus.write_byte_data(address, register, value)
        except OSError as exc:
            raise SensorReadError(
                "I2C write failed on "
                f"/dev/i2c-{self.bus_id} device=0x{address:02X} register=0x{register:02X} "
                f"value=0x{value:02X}: {exc}. Check sensor power, wiring, and configured address."
            ) from exc

    def write_word_data(self, address: int, register: int, value: int) -> None:
        try:
            self._bus.write_word_data(address, register, value)
        except OSError as exc:
            raise SensorReadError(
                "I2C write failed on "
                f"/dev/i2c-{self.bus_id} device=0x{address:02X} register=0x{register:02X} "
                f"value=0x{value:04X}: {exc}. Check sensor power, wiring, and configured address."
            ) from exc

    def close(self) -> None:
        self._bus.close()


class ADXL345:
    POWER_CTL = 0x2D
    DATA_FORMAT = 0x31
    DATAX0 = 0x32

    def __init__(self, bus: I2CBus, address: int) -> None:
        self.bus = bus
        self.address = address
        self.bus.write_byte_data(self.address, self.DATA_FORMAT, 0x0B)
        self.bus.write_byte_data(self.address, self.POWER_CTL, 0x08)

    @staticmethod
    def _signed_16(low: int, high: int) -> int:
        value = (high << 8) | low
        return value - 65536 if value & 0x8000 else value

    def read_axes_g(self) -> tuple[float, float, float]:
        data = self.bus.read_i2c_block_data(self.address, self.DATAX0, 6)
        x_raw = self._signed_16(data[0], data[1])
        y_raw = self._signed_16(data[2], data[3])
        z_raw = self._signed_16(data[4], data[5])
        scale = 0.0039
        return x_raw * scale, y_raw * scale, z_raw * scale


class ADS1115:
    POINTER_CONVERSION = 0x00
    POINTER_CONFIG = 0x01

    DATA_RATE_BITS = {
        8: 0b000,
        16: 0b001,
        32: 0b010,
        64: 0b011,
        128: 0b100,
        250: 0b101,
        475: 0b110,
        860: 0b111,
    }
    PGA_BITS = {
        6.144: 0b000,
        4.096: 0b001,
        2.048: 0b010,
        1.024: 0b011,
        0.512: 0b100,
        0.256: 0b101,
    }
    MUX_SINGLE_ENDED = {
        0: 0b100,
        1: 0b101,
        2: 0b110,
        3: 0b111,
    }

    def __init__(self, bus: I2CBus, address: int, gain: float, data_rate: int) -> None:
        if gain not in self.PGA_BITS:
            raise ValueError(f"Unsupported ADS1115 gain: {gain}")
        if data_rate not in self.DATA_RATE_BITS:
            raise ValueError(f"Unsupported ADS1115 data rate: {data_rate}")

        self.bus = bus
        self.address = address
        self.gain = gain
        self.data_rate = data_rate

    @staticmethod
    def _swap_word(value: int) -> int:
        return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)

    def read_single_ended_voltage(self, channel: int) -> float:
        if channel not in self.MUX_SINGLE_ENDED:
            raise ValueError(f"ADS1115 channel must be 0..3, got {channel}")

        config = (
            (1 << 15)
            | (self.MUX_SINGLE_ENDED[channel] << 12)
            | (self.PGA_BITS[self.gain] << 9)
            | (1 << 8)
            | (self.DATA_RATE_BITS[self.data_rate] << 5)
            | 0b11
        )
        self.bus.write_word_data(self.address, self.POINTER_CONFIG, self._swap_word(config))

        conversion_delay_s = (1.0 / self.data_rate) + 0.002
        time.sleep(conversion_delay_s)

        raw = self._swap_word(self.bus.read_word_data(self.address, self.POINTER_CONVERSION))
        if raw & 0x8000:
            raw -= 65536
        return (raw / 32768.0) * self.gain


class ACS712CurrentReader:
    def __init__(
        self,
        adc: ADS1115,
        channel: int,
        zero_voltage: float,
        sensitivity_volts_per_amp: float,
        voltage_divider_ratio: float,
        noise_floor_amps: float,
    ) -> None:
        if sensitivity_volts_per_amp <= 0:
            raise ValueError("ACS712 sensitivity must be positive")
        if voltage_divider_ratio <= 0:
            raise ValueError("ACS712 voltage divider ratio must be positive")

        self.adc = adc
        self.channel = channel
        self.zero_voltage = zero_voltage
        self.sensitivity_volts_per_amp = sensitivity_volts_per_amp
        self.voltage_divider_ratio = voltage_divider_ratio
        self.noise_floor_amps = noise_floor_amps

    def read_amps(self) -> float:
        measured_voltage = self.adc.read_single_ended_voltage(self.channel)
        sensor_voltage = measured_voltage * self.voltage_divider_ratio
        current = (sensor_voltage - self.zero_voltage) / self.sensitivity_volts_per_amp
        if abs(current) < self.noise_floor_amps:
            return 0.0
        return current


class DS18B20Reader:
    def __init__(self, device_path: str) -> None:
        self.device_path = Path(device_path)

    def read_celsius(self) -> float:
        try:
            lines = self.device_path.read_text(encoding="ascii").strip().splitlines()
        except FileNotFoundError as exc:
            raise SensorReadError(
                f"DS18B20 device file not found: {self.device_path}"
            ) from exc

        if len(lines) < 2 or not lines[0].strip().endswith("YES"):
            raise SensorReadError(f"DS18B20 CRC check failed for {self.device_path}")

        marker = "t="
        position = lines[1].find(marker)
        if position == -1:
            raise SensorReadError(f"DS18B20 temperature marker missing in {self.device_path}")
        return float(lines[1][position + len(marker):]) / 1000.0


class RealSensorReader:
    def __init__(self, settings: Settings) -> None:
        self.bus = I2CBus(settings.i2c_bus)
        try:
            self.accelerometer = ADXL345(self.bus, settings.adxl345_address)
            self.adc = ADS1115(
                self.bus,
                settings.ads1115_address,
                gain=settings.ads1115_gain,
                data_rate=settings.ads1115_data_rate,
            )
            self.current_sensor = ACS712CurrentReader(
                adc=self.adc,
                channel=settings.ads1115_channel,
                zero_voltage=settings.acs712_zero_voltage,
                sensitivity_volts_per_amp=settings.acs712_sensitivity,
                voltage_divider_ratio=settings.acs712_voltage_divider_ratio,
                noise_floor_amps=settings.current_noise_floor_amps,
            )
            self.temperature_sensor = DS18B20Reader(settings.ds18b20_device_path)
        except Exception:
            self.bus.close()
            raise

    def read(self) -> SensorSample:
        vib_x, vib_y, vib_z = self.accelerometer.read_axes_g()
        current = self.current_sensor.read_amps()
        temperature = self.temperature_sensor.read_celsius()

        return SensorSample(
            timestamp=datetime.now(timezone.utc).isoformat(),
            vib_x=vib_x,
            vib_y=vib_y,
            vib_z=vib_z,
            current=current,
            temperature=temperature,
        )

    def close(self) -> None:
        self.bus.close()


def build_sensor_reader(
    mode: str,
    fault_after_samples: int = 0,
    settings: Optional[Settings] = None,
) -> SupportsRead:
    runtime_settings = settings or SETTINGS
    if mode == "simulated":
        return SimulatedSensorReader(fault_after_samples=fault_after_samples)
    if mode == "real":
        return RealSensorReader(runtime_settings)
    raise ValueError(f"Unsupported sensor mode: {mode}")
