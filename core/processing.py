from __future__ import annotations

import math
from collections import deque
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Deque, Dict, List, Optional, Sequence

from core.schur import schur_health_index


@dataclass(frozen=True)
class SensorSample:
    timestamp: str
    vib_x: float
    vib_y: float
    vib_z: float
    current: float
    temperature: float

    def vector(self) -> List[float]:
        return [self.vib_x, self.vib_y, self.vib_z, self.current, self.temperature]


@dataclass(frozen=True)
class HealthAssessment:
    health_index: float
    z_score: float
    state: str
    motor_speed_ratio: float
    baseline_ready: bool
    triangular_matrix: List[List[float]]

    def as_payload(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["triangular_matrix"] = [
            [round(value, 6) for value in row] for row in self.triangular_matrix
        ]
        return payload


def mean(values: Sequence[float]) -> float:
    return fmean(values) if values else 0.0


def standard_deviation(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def covariance_matrix(samples: Sequence[Sequence[float]]) -> List[List[float]]:
    if not samples:
        raise ValueError("covariance_matrix requires at least one sample")

    feature_count = len(samples[0])
    sample_count = len(samples)
    means = [mean([sample[index] for sample in samples]) for index in range(feature_count)]
    centered = [
        [sample[index] - means[index] for index in range(feature_count)] for sample in samples
    ]

    matrix = [[0.0 for _ in range(feature_count)] for _ in range(feature_count)]
    divisor = max(sample_count - 1, 1)
    for row in range(feature_count):
        for col in range(feature_count):
            matrix[row][col] = (
                sum(centered[index][row] * centered[index][col] for index in range(sample_count))
                / divisor
            )
    return matrix


class MotorStateMachine:
    def __init__(
        self,
        reduced_threshold_z: float,
        stop_threshold_z: float,
        normal_speed_ratio: float = 1.0,
        reduced_speed_ratio: float = 0.6,
    ) -> None:
        self.reduced_threshold_z = reduced_threshold_z
        self.stop_threshold_z = stop_threshold_z
        self.normal_speed_ratio = normal_speed_ratio
        self.reduced_speed_ratio = reduced_speed_ratio
        self.state = "normal"

    def update(self, z_score: float, baseline_ready: bool) -> tuple[str, float]:
        if not baseline_ready:
            self.state = "normal"
        elif z_score >= self.stop_threshold_z:
            self.state = "stop"
        elif z_score >= self.reduced_threshold_z:
            self.state = "reduced"
        else:
            self.state = "normal"

        if self.state == "stop":
            return self.state, 0.0
        if self.state == "reduced":
            return self.state, self.reduced_speed_ratio
        return self.state, self.normal_speed_ratio


class FaultDetector:
    def __init__(
        self,
        window_size: int,
        baseline_windows: int,
        reduced_threshold_z: float,
        stop_threshold_z: float,
        normal_speed_ratio: float = 1.0,
        reduced_speed_ratio: float = 0.6,
    ) -> None:
        self.window: Deque[SensorSample] = deque(maxlen=window_size)
        self.baseline_indices: List[float] = []
        self.baseline_windows = baseline_windows
        self.state_machine = MotorStateMachine(
            reduced_threshold_z=reduced_threshold_z,
            stop_threshold_z=stop_threshold_z,
            normal_speed_ratio=normal_speed_ratio,
            reduced_speed_ratio=reduced_speed_ratio,
        )

    def process_sample(self, sample: SensorSample) -> Optional[HealthAssessment]:
        self.window.append(sample)
        if len(self.window) < self.window.maxlen:
            return None

        vectors = [entry.vector() for entry in self.window]
        covariance = covariance_matrix(vectors)
        health_index, triangular = schur_health_index(covariance)

        baseline_ready = len(self.baseline_indices) >= self.baseline_windows
        if not baseline_ready:
            self.baseline_indices.append(health_index)
            baseline_ready = len(self.baseline_indices) >= self.baseline_windows

        if baseline_ready:
            baseline_mean = mean(self.baseline_indices)
            baseline_std = standard_deviation(self.baseline_indices)
            if baseline_std <= 1e-12:
                z_score = float("inf") if health_index > baseline_mean else 0.0
            else:
                z_score = (health_index - baseline_mean) / baseline_std
        else:
            z_score = 0.0

        state, speed_ratio = self.state_machine.update(z_score, baseline_ready)
        return HealthAssessment(
            health_index=health_index,
            z_score=z_score,
            state=state,
            motor_speed_ratio=speed_ratio,
            baseline_ready=baseline_ready,
            triangular_matrix=triangular,
        )
