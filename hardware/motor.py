from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import SETTINGS, Settings


@dataclass
class MotorCommand:
    state: str
    speed_ratio: float
    pwm_value: int


class MockMotorController:
    def __init__(self) -> None:
        self.current_command = MotorCommand(state="stop", speed_ratio=0.0, pwm_value=0)

    def apply(self, state: str, speed_ratio: float) -> MotorCommand:
        clamped_ratio = max(0.0, min(speed_ratio, 1.0))
        pwm_value = int(round(clamped_ratio * 100))
        self.current_command = MotorCommand(state=state, speed_ratio=clamped_ratio, pwm_value=pwm_value)
        return self.current_command

    def stop(self) -> MotorCommand:
        return self.apply("stop", 0.0)

    def close(self) -> None:
        return None


class RealMotorController:
    def __init__(self, settings: Settings) -> None:
        try:
            from gpiozero import OutputDevice, PWMOutputDevice
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "gpiozero is required for MOTOR_MODE=real."
            ) from exc

        self.forward_pwm = PWMOutputDevice(
            pin=settings.motor_forward_pwm_pin,
            active_high=True,
            initial_value=0.0,
            frequency=settings.motor_pwm_frequency_hz,
        )
        self.reverse_pwm = PWMOutputDevice(
            pin=settings.motor_reverse_pwm_pin,
            active_high=True,
            initial_value=0.0,
            frequency=settings.motor_pwm_frequency_hz,
        )
        self.enable_right = OutputDevice(
            pin=settings.motor_enable_right_pin,
            active_high=True,
            initial_value=False,
        )
        self.enable_left = OutputDevice(
            pin=settings.motor_enable_left_pin,
            active_high=True,
            initial_value=False,
        )
        self.current_command = MotorCommand(state="stop", speed_ratio=0.0, pwm_value=0)
        self.stop()

    def _set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.enable_right.on()
            self.enable_left.on()
        else:
            self.enable_right.off()
            self.enable_left.off()

    def apply(self, state: str, speed_ratio: float) -> MotorCommand:
        clamped_ratio = max(0.0, min(speed_ratio, 1.0))
        if state == "stop" or clamped_ratio <= 0.0:
            return self.stop()

        self._set_enabled(True)
        self.forward_pwm.value = clamped_ratio
        self.reverse_pwm.value = 0.0
        self.current_command = MotorCommand(
            state=state,
            speed_ratio=clamped_ratio,
            pwm_value=int(round(clamped_ratio * 100)),
        )
        return self.current_command

    def stop(self) -> MotorCommand:
        self.forward_pwm.off()
        self.reverse_pwm.off()
        self._set_enabled(False)
        self.current_command = MotorCommand(state="stop", speed_ratio=0.0, pwm_value=0)
        return self.current_command

    def close(self) -> None:
        self.stop()
        self.forward_pwm.close()
        self.reverse_pwm.close()
        self.enable_right.close()
        self.enable_left.close()


def MotorController(
    mode: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> MockMotorController | RealMotorController:
    runtime_settings = settings or SETTINGS
    selected_mode = mode or runtime_settings.motor_mode
    if selected_mode == "mock":
        return MockMotorController()
    if selected_mode == "real":
        return RealMotorController(runtime_settings)
    raise ValueError(f"Unsupported motor mode: {selected_mode}")
