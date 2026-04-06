from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import SETTINGS
from core.processing import FaultDetector
from hardware.motor import MotorController
from hardware.sensors import DS18B20Reader, SensorReadError, build_sensor_reader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded sensor and runtime smoke test.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=25,
        help="Number of samples to read before exiting.",
    )
    parser.add_argument(
        "--sensor-mode",
        choices=("simulated", "real"),
        default=SETTINGS.sensor_mode,
        help="Sensor backend to use.",
    )
    parser.add_argument(
        "--motor-mode",
        choices=("mock", "real"),
        default="mock",
        help="Motor backend to use. Defaults to mock for safety.",
    )
    parser.add_argument(
        "--print-every",
        type=int,
        default=1,
        help="Print every Nth sample.",
    )
    return parser.parse_args()


def preflight_real_sensors() -> list[str]:
    issues: list[str] = []

    i2c_path = Path(f"/dev/i2c-{SETTINGS.i2c_bus}")
    if not i2c_path.exists():
        issues.append(
            f"Missing {i2c_path}. Enable I2C and verify the configured bus number."
        )

    try:
        DS18B20Reader(SETTINGS.ds18b20_device_path)
    except SensorReadError as exc:
        issues.append(str(exc))

    return issues


def build_detector() -> FaultDetector:
    return FaultDetector(
        window_size=SETTINGS.window_size,
        baseline_windows=SETTINGS.baseline_windows,
        reduced_threshold_z=SETTINGS.reduced_threshold_z,
        stop_threshold_z=SETTINGS.stop_threshold_z,
        reduced_clear_threshold_z=SETTINGS.reduced_clear_threshold_z,
        stop_clear_threshold_z=SETTINGS.stop_clear_threshold_z,
        normal_speed_ratio=SETTINGS.normal_speed_ratio,
        reduced_speed_ratio=SETTINGS.reduced_speed_ratio,
        z_score_smoothing_windows=SETTINGS.z_score_smoothing_windows,
        state_confirmation_windows=SETTINGS.state_confirmation_windows,
    )


def main() -> int:
    args = parse_args()
    if args.samples <= 0:
        raise SystemExit("--samples must be positive")
    if args.print_every <= 0:
        raise SystemExit("--print-every must be positive")

    if args.sensor_mode == "real":
        issues = preflight_real_sensors()
        if issues:
            print("Preflight failed:")
            for issue in issues:
                print(f"- {issue}")
            return 1

    detector = build_detector()
    sensor_reader = build_sensor_reader(
        mode=args.sensor_mode,
        fault_after_samples=SETTINGS.fault_after_samples,
        settings=SETTINGS,
    )
    motor = MotorController(mode=args.motor_mode, settings=SETTINGS)
    sample_interval = 1.0 / SETTINGS.sample_rate_hz

    currents: list[float] = []
    temperatures: list[float] = []
    health_indices: list[float] = []

    print(
        "Starting smoke test "
        f"sensor_mode={args.sensor_mode} motor_mode={args.motor_mode} "
        f"samples={args.samples} sample_rate_hz={SETTINGS.sample_rate_hz}"
    )

    try:
        for index in range(1, args.samples + 1):
            loop_started = time.monotonic()
            sample = sensor_reader.read()
            assessment = detector.process_sample(sample)

            currents.append(sample.current)
            temperatures.append(sample.temperature)

            if assessment is None:
                motor_command = motor.current_command
                baseline_ready = False
                z_score = None
                state = motor_command.state
            else:
                health_indices.append(assessment.health_index)
                motor_command = motor.apply(assessment.state, assessment.motor_speed_ratio)
                baseline_ready = assessment.baseline_ready
                z_score = assessment.z_score
                state = assessment.state

            if index % args.print_every == 0:
                sample_payload = asdict(sample)
                print(
                    f"sample={index} sensor={sample_payload} "
                    f"state={state} baseline_ready={baseline_ready} z_score={z_score} "
                    f"motor={asdict(motor_command)}"
                )

            elapsed = time.monotonic() - loop_started
            if elapsed < sample_interval:
                time.sleep(sample_interval - elapsed)
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as exc:
        print(f"Smoke test failed: {exc}")
        return 1
    finally:
        motor.close()
        sensor_reader.close()

    current_mean = statistics.fmean(currents)
    temperature_mean = statistics.fmean(temperatures)
    health_summary = "baseline_not_ready"
    if health_indices:
        health_summary = (
            f"health_index_min={min(health_indices):.6f} "
            f"health_index_max={max(health_indices):.6f}"
        )

    print(
        "Smoke test passed "
        f"current_mean={current_mean:.4f}A "
        f"temperature_mean={temperature_mean:.4f}C "
        f"{health_summary}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
