import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from config import Settings
from hardware.sensors import DS18B20Reader, I2CBus, RealSensorReader, SensorReadError


class _FailingSMBus:
    def write_byte_data(self, address: int, register: int, value: int) -> None:
        raise OSError(121, "Remote I/O error")


class _FakeBus:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _MissingBusFactory:
    def __init__(self, bus_id: int) -> None:
        raise FileNotFoundError(2, "No such file or directory", f"/dev/i2c-{bus_id}")


class SensorTests(unittest.TestCase):
    def test_ds18b20_reader_auto_discovers_probe_from_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            probe_file = Path(temp_dir) / "28-000000000001" / "w1_slave"
            probe_file.parent.mkdir()
            probe_file.write_text(
                "aa bb cc dd ee ff gg hh ii : crc=ii YES\n"
                "aa bb cc dd ee ff gg hh ii t=23125\n",
                encoding="ascii",
            )

            reader = DS18B20Reader(temp_dir)

            self.assertEqual(reader.device_path, probe_file)
            self.assertEqual(reader.read_celsius(), 23.125)

    def test_ds18b20_reader_raises_when_directory_has_no_probe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(SensorReadError) as context:
                DS18B20Reader(temp_dir)

        self.assertIn("No DS18B20 device file found", str(context.exception))

    def test_i2c_bus_open_wraps_missing_device_error(self) -> None:
        with patch("smbus2.SMBus", _MissingBusFactory):
            with self.assertRaises(SensorReadError) as context:
                I2CBus(1)

        self.assertIn("/dev/i2c-1", str(context.exception))

    def test_i2c_write_wraps_oserror_with_bus_and_device_context(self) -> None:
        bus = I2CBus.__new__(I2CBus)
        bus.bus_id = 1
        bus._bus = _FailingSMBus()

        with self.assertRaises(SensorReadError) as context:
            bus.write_byte_data(0x53, 0x31, 0x0B)

        message = str(context.exception)
        self.assertIn("/dev/i2c-1", message)
        self.assertIn("device=0x53", message)
        self.assertIn("register=0x31", message)

    def test_real_sensor_reader_closes_bus_on_startup_failure(self) -> None:
        fake_bus = _FakeBus()

        with patch("hardware.sensors.I2CBus", return_value=fake_bus):
            with patch("hardware.sensors.ADXL345", side_effect=SensorReadError("boom")):
                with self.assertRaises(SensorReadError):
                    RealSensorReader(Settings())

        self.assertTrue(fake_bus.closed)


if __name__ == "__main__":
    unittest.main()
