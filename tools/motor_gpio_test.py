from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import SETTINGS
from hardware.motor import MotorController


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded direct motor GPIO test.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.2,
        help="Motor speed ratio in the range 0.0..1.0. Defaults to 0.2.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="Seconds to drive the motor before stopping. Defaults to 3.0.",
    )
    parser.add_argument(
        "--state",
        choices=("normal", "reduced"),
        default="normal",
        help="Logical motor state to apply. Defaults to normal.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.speed <= 1.0:
        raise SystemExit("--speed must be between 0.0 and 1.0")
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")

    motor = MotorController(mode="real", settings=SETTINGS)
    print(
        "Starting direct motor test "
        f"forward_pwm_pin={SETTINGS.motor_forward_pwm_pin} "
        f"reverse_pwm_pin={SETTINGS.motor_reverse_pwm_pin} "
        f"enable_right_pin={SETTINGS.motor_enable_right_pin} "
        f"enable_left_pin={SETTINGS.motor_enable_left_pin} "
        f"speed={args.speed:.2f} duration={args.duration:.2f}s state={args.state}"
    )

    try:
        command = motor.apply(args.state, args.speed)
        print(
            "Motor command applied "
            f"state={command.state} speed_ratio={command.speed_ratio:.2f} pwm_value={command.pwm_value}"
        )
        time.sleep(args.duration)
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    finally:
        stopped = motor.stop()
        motor.close()
        print(
            "Motor stopped "
            f"state={stopped.state} speed_ratio={stopped.speed_ratio:.2f} pwm_value={stopped.pwm_value}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
