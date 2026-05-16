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
    raw_z_score: float
    state: str
    motor_speed_ratio: float
    baseline_ready: bool
    vibration_rms: float
    override_reason: Optional[str]
    triangular_matrix: List[List[float]]

    def as_payload(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["triangular_matrix"] = [
            [round(value, 6) for value in row] for row in self.triangular_matrix
        ]
        return payload


def mean(values: Sequence[float]) -> float:
    return fmean(values) if values else 0.0


def vibration_rms(sample: SensorSample) -> float:
    return math.sqrt(
        (sample.vib_x * sample.vib_x + sample.vib_y * sample.vib_y + sample.vib_z * sample.vib_z) / 3.0
    )


def standard_deviation(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def sensitive_z_score(values: Sequence[float], latest_value: float) -> float:
    averaged = mean(values)
    latest_severity = abs(latest_value)
    average_severity = mean([abs(value) for value in values])
    peak_severity = max((abs(value) for value in values), default=0.0)

    if latest_value * averaged >= 0:
        boosted_severity = latest_severity + average_severity + (0.25 * peak_severity)
    else:
        boosted_severity = latest_severity

    if latest_severity > 0.0:
        return math.copysign(max(latest_severity, abs(averaged), boosted_severity), latest_value)
    if averaged != 0.0:
        return math.copysign(max(abs(averaged), boosted_severity), averaged)
    return 0.0


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
        reduced_clear_threshold_z: Optional[float] = None,
        stop_clear_threshold_z: Optional[float] = None,
        normal_speed_ratio: float = 1.0,
        reduced_speed_ratio: float = 0.6,
        confirmation_windows: int = 1,
    ) -> None:
        self.reduced_threshold_z = reduced_threshold_z
        self.stop_threshold_z = stop_threshold_z
        self.reduced_clear_threshold_z = (
            reduced_clear_threshold_z
            if reduced_clear_threshold_z is not None
            else reduced_threshold_z
        )
        self.stop_clear_threshold_z = (
            stop_clear_threshold_z if stop_clear_threshold_z is not None else stop_threshold_z
        )
        self.normal_speed_ratio = normal_speed_ratio
        self.reduced_speed_ratio = reduced_speed_ratio
        self.confirmation_windows = max(1, confirmation_windows)
        self.state = "normal"
        self.pending_state: Optional[str] = None
        self.pending_count = 0

    def update(self, z_score: float, baseline_ready: bool) -> tuple[str, float]:
        severity = abs(z_score)
        if not baseline_ready:
            target_state = "stop"
        elif self.state == "stop":
            if severity >= self.stop_clear_threshold_z:
                target_state = "stop"
            elif severity >= self.reduced_clear_threshold_z:
                target_state = "reduced"
            else:
                target_state = "normal"
        elif self.state == "reduced":
            if severity >= self.stop_threshold_z:
                target_state = "stop"
            elif severity < self.reduced_clear_threshold_z:
                target_state = "normal"
            else:
                target_state = "reduced"
        else:
            if severity >= self.stop_threshold_z:
                target_state = "stop"
            elif severity >= self.reduced_threshold_z:
                target_state = "reduced"
            else:
                target_state = "normal"

        if target_state != self.state:
            if target_state == self.pending_state:
                self.pending_count += 1
            else:
                self.pending_state = target_state
                self.pending_count = 1
            if self.pending_count >= self.confirmation_windows:
                self.state = target_state
                self.pending_state = None
                self.pending_count = 0
        else:
            self.pending_state = None
            self.pending_count = 0

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
        reduced_clear_threshold_z: Optional[float] = None,
        stop_clear_threshold_z: Optional[float] = None,
        normal_speed_ratio: float = 1.0,
        reduced_speed_ratio: float = 0.6,
        reduced_vibration_rms_threshold: Optional[float] = None,
        stop_vibration_rms_threshold: Optional[float] = None,
        reduced_temperature_c_threshold: Optional[float] = None,
        stop_temperature_c_threshold: Optional[float] = None,
        z_score_smoothing_windows: int = 1,
        state_confirmation_windows: int = 1,
    ) -> None:
        self.window: Deque[SensorSample] = deque(maxlen=window_size)
        self.baseline_indices: List[float] = []
        self.baseline_windows = baseline_windows
        self.z_scores: Deque[float] = deque(maxlen=max(1, z_score_smoothing_windows))
        self.normal_speed_ratio = normal_speed_ratio
        self.reduced_speed_ratio = reduced_speed_ratio
        self.reduced_vibration_rms_threshold = reduced_vibration_rms_threshold
        self.stop_vibration_rms_threshold = stop_vibration_rms_threshold
        self.reduced_temperature_c_threshold = reduced_temperature_c_threshold
        self.stop_temperature_c_threshold = stop_temperature_c_threshold
        self.state_machine = MotorStateMachine(
            reduced_threshold_z=reduced_threshold_z,
            stop_threshold_z=stop_threshold_z,
            reduced_clear_threshold_z=reduced_clear_threshold_z,
            stop_clear_threshold_z=stop_clear_threshold_z,
            normal_speed_ratio=normal_speed_ratio,
            reduced_speed_ratio=reduced_speed_ratio,
            confirmation_windows=state_confirmation_windows,
        )

    @staticmethod
    def _state_rank(state: str) -> int:
        if state == "stop":
            return 2
        if state == "reduced":
            return 1
        return 0

    def _apply_direct_limits(
        self,
        base_state: str,
        sample: SensorSample,
        sample_vibration_rms: float,
    ) -> tuple[str, float, Optional[str]]:
        triggered: list[tuple[str, str]] = []

        if (
            self.stop_vibration_rms_threshold is not None
            and sample_vibration_rms >= self.stop_vibration_rms_threshold
        ):
            triggered.append(("stop", "vibration_rms"))
        elif (
            self.reduced_vibration_rms_threshold is not None
            and sample_vibration_rms >= self.reduced_vibration_rms_threshold
        ):
            triggered.append(("reduced", "vibration_rms"))

        if (
            self.stop_temperature_c_threshold is not None
            and sample.temperature >= self.stop_temperature_c_threshold
        ):
            triggered.append(("stop", "temperature"))
        elif (
            self.reduced_temperature_c_threshold is not None
            and sample.temperature >= self.reduced_temperature_c_threshold
        ):
            triggered.append(("reduced", "temperature"))

        if not triggered:
            return base_state, (
                0.0
                if base_state == "stop"
                else self.reduced_speed_ratio if base_state == "reduced" else self.normal_speed_ratio
            ), None

        override_state, reason = max(triggered, key=lambda item: self._state_rank(item[0]))
        if self._state_rank(override_state) < self._state_rank(base_state):
            override_state = base_state
            reason = None

        if override_state == "stop":
            return "stop", 0.0, reason
        if override_state == "reduced":
            return "reduced", self.reduced_speed_ratio, reason
        return "normal", self.normal_speed_ratio, reason

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
                raw_z_score = float("inf") if health_index > baseline_mean else 0.0
            else:
                raw_z_score = (health_index - baseline_mean) / baseline_std
        else:
            raw_z_score = 0.0

        self.z_scores.append(raw_z_score)
        z_score = sensitive_z_score(self.z_scores, raw_z_score)
        state, speed_ratio = self.state_machine.update(z_score, baseline_ready)
        sample_vibration_rms = vibration_rms(sample)
        state, speed_ratio, override_reason = self._apply_direct_limits(state, sample, sample_vibration_rms)
        return HealthAssessment(
            health_index=health_index,
            z_score=z_score,
            raw_z_score=raw_z_score,
            state=state,
            motor_speed_ratio=speed_ratio,
            baseline_ready=baseline_ready,
            vibration_rms=sample_vibration_rms,
            override_reason=override_reason,
            triangular_matrix=triangular,
        )
