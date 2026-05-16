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

    def test_ds18b20_reader_reuses_cached_value_within_min_interval(self) -> None:
        with TemporaryDirectory() as temp_dir:
            probe_file = Path(temp_dir) / "28-000000000001" / "w1_slave"
            probe_file.parent.mkdir()
            probe_file.write_text(
                "aa bb cc dd ee ff gg hh ii : crc=ii YES\n"
                "aa bb cc dd ee ff gg hh ii t=23125\n",
                encoding="ascii",
            )

            reader = DS18B20Reader(temp_dir, min_read_interval_s=0.75)

            with patch("hardware.sensors.time.monotonic", side_effect=[10.0, 10.2, 11.0]):
                first = reader.read_celsius()
                probe_file.write_text(
                    "aa bb cc dd ee ff gg hh ii : crc=ii YES\n"
                    "aa bb cc dd ee ff gg hh ii t=25000\n",
                    encoding="ascii",
                )
                second = reader.read_celsius()
                third = reader.read_celsius()

        self.assertEqual(first, 23.125)
        self.assertEqual(second, 23.125)
        self.assertEqual(third, 25.0)

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

    def test_real_sensor_reader_passes_ds18b20_read_interval_setting(self) -> None:
        fake_bus = _FakeBus()
        settings = Settings(ds18b20_min_read_interval_s=1.25)

        with patch("hardware.sensors.I2CBus", return_value=fake_bus):
            with patch("hardware.sensors.ADXL345"):
                with patch("hardware.sensors.ADS1115"):
                    with patch("hardware.sensors.ACS712CurrentReader"):
                        with patch("hardware.sensors.DS18B20Reader") as ds18b20_reader:
                            reader = RealSensorReader(settings)

        ds18b20_reader.assert_called_once_with(
            settings.ds18b20_device_path,
            min_read_interval_s=1.25,
        )
        reader.close()
        self.assertTrue(fake_bus.closed)


if __name__ == "__main__":
    unittest.main()
