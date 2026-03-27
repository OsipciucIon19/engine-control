from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import asdict
from typing import Optional

from config import SETTINGS
from core.processing import FaultDetector, HealthAssessment, SensorSample
from hardware.gpio_setup import setup_gpio
from hardware.motor import MotorController
from hardware.sensors import build_sensor_reader
from services.api_client import ApiClient
from utils.logger import configure_logging


logger = logging.getLogger(__name__)


def collect_payload(
    sample: SensorSample,
    assessment: Optional[HealthAssessment],
    motor_state: str,
    motor_speed_ratio: float,
) -> dict:
    payload = {
        "timestamp": sample.timestamp,
        "sensor": asdict(sample),
        "motor": {
            "state": motor_state,
            "speed_ratio": motor_speed_ratio,
        },
    }
    if assessment is not None:
        payload["algorithm"] = assessment.as_payload()
    return payload


def sender_loop(send_queue: "queue.Queue[list[dict]]", api_client: ApiClient) -> None:
    while True:
        batch = send_queue.get()
        try:
            api_client.send_batch(batch)
        finally:
            send_queue.task_done()


def main() -> None:
    configure_logging()
    setup_gpio()

    sample_interval = 1.0 / SETTINGS.sample_rate_hz
    sensor_reader = build_sensor_reader(
        mode=SETTINGS.sensor_mode,
        fault_after_samples=SETTINGS.fault_after_samples,
    )
    detector = FaultDetector(
        window_size=SETTINGS.window_size,
        baseline_windows=SETTINGS.baseline_windows,
        reduced_threshold_z=SETTINGS.reduced_threshold_z,
        stop_threshold_z=SETTINGS.stop_threshold_z,
        normal_speed_ratio=SETTINGS.normal_speed_ratio,
        reduced_speed_ratio=SETTINGS.reduced_speed_ratio,
    )
    motor = MotorController()
    api_client = ApiClient(
        device_id=SETTINGS.device_id,
        endpoint=SETTINGS.api_endpoint,
        enabled=SETTINGS.sender_enabled,
    )

    send_queue: "queue.Queue[list[dict]]" = queue.Queue()
    threading.Thread(target=sender_loop, args=(send_queue, api_client), daemon=True).start()

    buffer: list[dict] = []
    last_send_time = time.monotonic()

    while True:
        loop_started = time.monotonic()
        sample = sensor_reader.read()
        assessment = detector.process_sample(sample)

        if assessment is None:
            motor_command = motor.current_command
        else:
            motor_command = motor.apply(assessment.state, assessment.motor_speed_ratio)
            logger.info(
                "health_index=%.6f z_score=%.3f state=%s speed_ratio=%.2f baseline_ready=%s",
                assessment.health_index,
                assessment.z_score,
                assessment.state,
                assessment.motor_speed_ratio,
                assessment.baseline_ready,
            )

        buffer.append(
            collect_payload(
                sample=sample,
                assessment=assessment,
                motor_state=motor_command.state,
                motor_speed_ratio=motor_command.speed_ratio,
            )
        )

        now = time.monotonic()
        if len(buffer) >= SETTINGS.batch_size or (now - last_send_time) >= SETTINGS.send_interval:
            send_queue.put(buffer.copy())
            buffer.clear()
            last_send_time = now

        elapsed = time.monotonic() - loop_started
        if elapsed < sample_interval:
            time.sleep(sample_interval - elapsed)


if __name__ == "__main__":
    main()
