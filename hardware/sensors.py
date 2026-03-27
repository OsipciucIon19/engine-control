from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Optional

from core.processing import SensorSample


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


class FixedSampleSensorReader:
    def __init__(self, sample: SensorSample) -> None:
        self.sample = sample

    def read(self) -> SensorSample:
        return self.sample


def build_sensor_reader(mode: str, fault_after_samples: int = 0) -> SimulatedSensorReader:
    if mode != "simulated":
        raise ValueError(f"Unsupported sensor mode: {mode}")
    return SimulatedSensorReader(fault_after_samples=fault_after_samples)
