from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MotorCommand:
    state: str
    speed_ratio: float
    pwm_value: int


class MotorController:
    def __init__(self) -> None:
        self.current_command = MotorCommand(state="normal", speed_ratio=1.0, pwm_value=100)

    def apply(self, state: str, speed_ratio: float) -> MotorCommand:
        clamped_ratio = max(0.0, min(speed_ratio, 1.0))
        pwm_value = int(round(clamped_ratio * 100))
        self.current_command = MotorCommand(state=state, speed_ratio=clamped_ratio, pwm_value=pwm_value)
        return self.current_command
