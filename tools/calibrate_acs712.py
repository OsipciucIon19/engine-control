from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import SETTINGS
from hardware.sensors import ADS1115, I2CBus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calibrate ACS712 zero offset and inspect ADS1115 readings.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=200,
        help="Number of samples to capture. Defaults to 200.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.02,
        help="Seconds between samples. Defaults to 0.02.",
    )
    parser.add_argument(
        "--reference-current",
        type=float,
        default=None,
        help="Known current in amps from a multimeter to estimate divider ratio.",
    )
    parser.add_argument(
        "--zero-voltage",
        type=float,
        default=None,
        help="Override zero voltage for computed current and divider estimation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.samples <= 0:
        raise SystemExit("--samples must be positive")
    if args.interval <= 0:
        raise SystemExit("--interval must be positive")
    if args.reference_current is not None and args.reference_current < 0:
        raise SystemExit("--reference-current must be zero or positive")

    bus = I2CBus(SETTINGS.i2c_bus)
    adc = ADS1115(
        bus,
        SETTINGS.ads1115_address,
        SETTINGS.ads1115_gain,
        SETTINGS.ads1115_data_rate,
    )
    zero_voltage = args.zero_voltage if args.zero_voltage is not None else SETTINGS.acs712_zero_voltage

    measured_voltages: list[float] = []
    sensor_voltages: list[float] = []
    currents: list[float] = []

    print(
        "Sampling ACS712 "
        f"ads1115_address=0x{SETTINGS.ads1115_address:02X} "
        f"channel={SETTINGS.ads1115_channel} "
        f"gain={SETTINGS.ads1115_gain} "
        f"data_rate={SETTINGS.ads1115_data_rate} "
        f"sensitivity={SETTINGS.acs712_sensitivity:.3f}V/A "
        f"divider_ratio={SETTINGS.acs712_voltage_divider_ratio:.4f}"
    )

    try:
        for index in range(1, args.samples + 1):
            measured_voltage = adc.read_single_ended_voltage(SETTINGS.ads1115_channel)
            sensor_voltage = measured_voltage * SETTINGS.acs712_voltage_divider_ratio
            current = (sensor_voltage - zero_voltage) / SETTINGS.acs712_sensitivity
            measured_voltages.append(measured_voltage)
            sensor_voltages.append(sensor_voltage)
            currents.append(current)
            if index == 1 or index == args.samples or index % max(1, args.samples // 10) == 0:
                print(
                    f"sample={index} "
                    f"adc_voltage={measured_voltage:.4f}V "
                    f"sensor_voltage={sensor_voltage:.4f}V "
                    f"current={current:.4f}A"
                )
            time.sleep(args.interval)
    finally:
        bus.close()

    avg_adc_voltage = statistics.fmean(measured_voltages)
    avg_sensor_voltage = statistics.fmean(sensor_voltages)
    avg_current = statistics.fmean(currents)
    stdev_current = statistics.pstdev(currents) if len(currents) > 1 else 0.0

    print("")
    print("Summary")
    print(f"avg_adc_voltage={avg_adc_voltage:.6f}V")
    print(f"avg_sensor_voltage={avg_sensor_voltage:.6f}V")
    print(f"min_sensor_voltage={min(sensor_voltages):.6f}V")
    print(f"max_sensor_voltage={max(sensor_voltages):.6f}V")
    print(f"avg_current={avg_current:.6f}A")
    print(f"current_stdev={stdev_current:.6f}A")
    print("")
    print("Recommended .env values")
    print(f"ACS712_SENSITIVITY=0.1")
    print(f"ACS712_ZERO_VOLTAGE={avg_sensor_voltage:.6f}")

    if args.reference_current is not None:
        expected_sensor_voltage = (
            zero_voltage
            + args.reference_current * SETTINGS.acs712_sensitivity
        )
        recommended_divider_ratio = expected_sensor_voltage / avg_adc_voltage if avg_adc_voltage else 0.0
        print(f"ACS712_VOLTAGE_DIVIDER_RATIO={recommended_divider_ratio:.6f}")
        print("")
        print(
            "Reference comparison "
            f"reference_current={args.reference_current:.6f}A "
            f"expected_sensor_voltage={expected_sensor_voltage:.6f}V"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
