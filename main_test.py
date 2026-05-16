from __future__ import annotations

import argparse
import signal
import statistics
import time
from typing import Optional

from config import SETTINGS
from hardware.gpio_setup import setup_gpio
from hardware.motor import MotorController
from hardware.sensors import ACS712CurrentReader, ADS1115, I2CBus, SensorReadError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual motor control test entrypoint for Raspberry Pi.",
    )
    parser.add_argument(
        "--pin-check",
        action="store_true",
        help="Run a GPIO diagnostic sequence on BTS7960 pins instead of a motor run.",
    )
    parser.add_argument(
        "--pin-check-hold",
        type=float,
        default=2.0,
        help="Seconds to hold each diagnostic pin state. Defaults to 2.0.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.35,
        help="Target motor speed ratio in the range 0.0..1.0. Defaults to 0.35.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Seconds to hold the target speed. Defaults to 5.0.",
    )
    parser.add_argument(
        "--state",
        choices=("normal", "reduced"),
        default="normal",
        help="Logical motor state to apply. Defaults to normal.",
    )
    parser.add_argument(
        "--ramp-duration",
        type=float,
        default=1.5,
        help="Seconds used to ramp from 0 to target speed. Use 0 to disable. Defaults to 1.5.",
    )
    parser.add_argument(
        "--ramp-steps",
        type=int,
        default=5,
        help="Number of speed ramp steps. Defaults to 5.",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=1.0,
        help="Seconds to wait after stop before exit. Defaults to 1.0.",
    )
    parser.add_argument(
        "--with-current",
        action="store_true",
        help="Also read the ACS712 current sensor through ADS1115 during the run.",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=0.1,
        help="Seconds between current samples when --with-current is enabled. Defaults to 0.1.",
    )
    parser.add_argument(
        "--print-every",
        type=int,
        default=1,
        help="Print every Nth current sample. Defaults to 1.",
    )
    return parser.parse_args()


def build_current_sensor() -> tuple[ACS712CurrentReader, I2CBus]:
    bus = I2CBus(SETTINGS.i2c_bus)
    adc = ADS1115(
        bus,
        SETTINGS.ads1115_address,
        SETTINGS.ads1115_gain,
        SETTINGS.ads1115_data_rate,
    )
    current_sensor = ACS712CurrentReader(
        adc=adc,
        channel=SETTINGS.ads1115_channel,
        zero_voltage=SETTINGS.acs712_zero_voltage,
        sensitivity_volts_per_amp=SETTINGS.acs712_sensitivity,
        voltage_divider_ratio=SETTINGS.acs712_voltage_divider_ratio,
        noise_floor_amps=SETTINGS.current_noise_floor_amps,
    )
    return current_sensor, bus


def sleep_until(deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


def run_pin_check(hold_seconds: float) -> int:
    try:
        from gpiozero import OutputDevice, PWMOutputDevice
        from gpiozero.exc import BadPinFactory, GPIOZeroError
    except ModuleNotFoundError as exc:
        raise SystemExit("gpiozero is required for --pin-check") from exc

    try:
        forward_pwm = PWMOutputDevice(
            pin=SETTINGS.motor_forward_pwm_pin,
            active_high=True,
            initial_value=0.0,
            frequency=SETTINGS.motor_pwm_frequency_hz,
        )
        reverse_pwm = PWMOutputDevice(
            pin=SETTINGS.motor_reverse_pwm_pin,
            active_high=True,
            initial_value=0.0,
            frequency=SETTINGS.motor_pwm_frequency_hz,
        )
        enable_right = OutputDevice(
            pin=SETTINGS.motor_enable_right_pin,
            active_high=True,
            initial_value=False,
        )
        enable_left = OutputDevice(
            pin=SETTINGS.motor_enable_left_pin,
            active_high=True,
            initial_value=False,
        )
    except (BadPinFactory, GPIOZeroError) as exc:
        raise SystemExit(f"GPIO setup failed for --pin-check: {exc}") from exc

    print(
        "Starting BTS7960 GPIO pin check "
        f"forward_pwm_pin={SETTINGS.motor_forward_pwm_pin} "
        f"reverse_pwm_pin={SETTINGS.motor_reverse_pwm_pin} "
        f"enable_right_pin={SETTINGS.motor_enable_right_pin} "
        f"enable_left_pin={SETTINGS.motor_enable_left_pin} "
        f"hold={hold_seconds:.2f}s"
    )

    try:
        print("Step 1: R_EN HIGH, L_EN HIGH, PWM LOW")
        enable_right.on()
        enable_left.on()
        forward_pwm.off()
        reverse_pwm.off()
        time.sleep(hold_seconds)

        print("Step 2: R_EN HIGH, L_EN HIGH, RPWM 50%, LPWM LOW")
        forward_pwm.value = 0.5
        reverse_pwm.off()
        time.sleep(hold_seconds)

        print("Step 3: R_EN HIGH, L_EN HIGH, RPWM LOW, LPWM 50%")
        enable_right.on()
        enable_left.on()
        forward_pwm.off()
        reverse_pwm.value = 0.5
        time.sleep(hold_seconds)

        print("Step 4: all outputs LOW")
        forward_pwm.off()
        reverse_pwm.off()
        enable_right.off()
        enable_left.off()
        time.sleep(hold_seconds)
    finally:
        forward_pwm.close()
        reverse_pwm.close()
        enable_right.close()
        enable_left.close()

    return 0


def run_speed_ramp(
    motor: object,
    state: str,
    target_speed: float,
    ramp_duration: float,
    ramp_steps: int,
) -> None:
    if ramp_duration <= 0 or target_speed <= 0:
        command = motor.apply(state, target_speed)
        print(
            "Motor command applied "
            f"state={command.state} speed_ratio={command.speed_ratio:.2f} pwm_value={command.pwm_value}"
        )
        return

    steps = max(1, ramp_steps)
    step_duration = ramp_duration / steps
    for index in range(1, steps + 1):
        step_speed = target_speed * index / steps
        command = motor.apply(state, step_speed)
        print(
            "Ramp step "
            f"{index}/{steps} state={command.state} speed_ratio={command.speed_ratio:.2f} "
            f"pwm_value={command.pwm_value}"
        )
        time.sleep(step_duration)


def monitor_current(
    current_sensor: ACS712CurrentReader,
    duration: float,
    sample_interval: float,
    print_every: int,
) -> list[float]:
    currents: list[float] = []
    deadline = time.monotonic() + duration
    sample_index = 0
    while time.monotonic() < deadline:
        loop_started = time.monotonic()
        sample_index += 1
        current = current_sensor.read_amps()
        currents.append(current)
        if sample_index % print_every == 0:
            print(f"sample={sample_index} current={current:.4f}A")
        sleep_until(loop_started + sample_interval)
    return currents


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.speed <= 1.0:
        raise SystemExit("--speed must be between 0.0 and 1.0")
    if args.pin_check_hold <= 0:
        raise SystemExit("--pin-check-hold must be positive")
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    if args.ramp_duration < 0:
        raise SystemExit("--ramp-duration must be zero or positive")
    if args.ramp_steps <= 0:
        raise SystemExit("--ramp-steps must be positive")
    if args.cooldown < 0:
        raise SystemExit("--cooldown must be zero or positive")
    if args.sample_interval <= 0:
        raise SystemExit("--sample-interval must be positive")
    if args.print_every <= 0:
        raise SystemExit("--print-every must be positive")

    setup_gpio()

    if args.pin_check:
        return run_pin_check(args.pin_check_hold)

    motor = MotorController(mode="real", settings=SETTINGS)
    current_sensor: Optional[ACS712CurrentReader] = None
    bus: Optional[I2CBus] = None
    currents: list[float] = []
    interrupted = False

    def handle_signal(signum: int, frame: object) -> None:
        del signum, frame
        nonlocal interrupted
        interrupted = True
        raise KeyboardInterrupt

    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        if args.with_current:
            current_sensor, bus = build_current_sensor()

        print(
            "Starting motor test "
            f"forward_pwm_pin={SETTINGS.motor_forward_pwm_pin} "
            f"reverse_pwm_pin={SETTINGS.motor_reverse_pwm_pin} "
            f"enable_right_pin={SETTINGS.motor_enable_right_pin} "
            f"enable_left_pin={SETTINGS.motor_enable_left_pin} "
            f"speed={args.speed:.2f} duration={args.duration:.2f}s "
            f"state={args.state} ramp_duration={args.ramp_duration:.2f}s "
            f"ramp_steps={args.ramp_steps} current_monitoring={args.with_current}"
        )
        if args.with_current:
            print(
                "Current sensor config "
                f"ads1115_address=0x{SETTINGS.ads1115_address:02X} "
                f"ads1115_channel={SETTINGS.ads1115_channel} "
                f"sample_interval={args.sample_interval:.3f}s"
            )

        run_speed_ramp(
            motor=motor,
            state=args.state,
            target_speed=args.speed,
            ramp_duration=args.ramp_duration,
            ramp_steps=args.ramp_steps,
        )

        if current_sensor is not None:
            currents = monitor_current(
                current_sensor=current_sensor,
                duration=args.duration,
                sample_interval=args.sample_interval,
                print_every=args.print_every,
            )
        else:
            print(f"Holding target speed for {args.duration:.2f}s")
            time.sleep(args.duration)

    except SensorReadError as exc:
        print(f"Current sensor startup failed: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)

        stopped = motor.stop()
        print(
            "Motor stopped "
            f"state={stopped.state} speed_ratio={stopped.speed_ratio:.2f} pwm_value={stopped.pwm_value}"
        )
        if args.cooldown > 0:
            print(f"Cooldown for {args.cooldown:.2f}s")
            time.sleep(args.cooldown)
        motor.close()
        if bus is not None:
            bus.close()
        if currents:
            print(
                "Current summary "
                f"samples={len(currents)} "
                f"min={min(currents):.4f}A max={max(currents):.4f}A "
                f"avg={statistics.fmean(currents):.4f}A"
            )

    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
