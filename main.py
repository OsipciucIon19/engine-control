from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from config import SETTINGS
from core.processing import FaultDetector, HealthAssessment, SensorSample
from hardware.gpio_setup import setup_gpio
from hardware.motor import MotorController
from hardware.sensors import SensorReadError, build_sensor_reader
from services.api_client import ApiClient
from utils.logger import configure_logging


logger = logging.getLogger(__name__)
SEND_STOP = object()


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


def flush_buffer(
    buffer: list[dict],
    send_queue: "queue.Queue[list[dict] | object]",
) -> None:
    if not buffer:
        return
    send_queue.put(buffer.copy())
    buffer.clear()


def spool_batch(batch: list[dict], spool_path: Path) -> None:
    spool_path.parent.mkdir(parents=True, exist_ok=True)
    with spool_path.open("a", encoding="utf-8") as handle:
        json.dump(batch, handle)
        handle.write("\n")


def enqueue_spooled_batches(
    send_queue: "queue.Queue[list[dict] | object]",
    spool_path: Path,
) -> None:
    pending_path = spool_path.with_suffix(f"{spool_path.suffix}.pending")
    
    def process_path(path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    payload = line.strip()
                    if not payload:
                        continue
                    try:
                        batch = json.loads(payload)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Skipping invalid spooled batch line %s from %s",
                            line_number,
                            path,
                        )
                        continue
                    if isinstance(batch, list) and batch:
                        send_queue.put(batch)
        finally:
            path.unlink(missing_ok=True)

    if pending_path.exists():
        process_path(pending_path)

    if spool_path.exists():
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        spool_path.replace(pending_path)
        process_path(pending_path)


def sender_loop(
    send_queue: "queue.Queue[list[dict] | object]",
    api_client: ApiClient,
    retry_interval: float,
    max_retries: int,
    spool_path: Path,
) -> None:
    while True:
        item = send_queue.get()
        try:
            if item is SEND_STOP:
                return

            batch = item
            attempts = 0
            while True:
                result = api_client.send_batch(batch)
                if result in {"sent", "skipped"}:
                    break

                attempts += 1
                if max_retries > 0 and attempts >= max_retries:
                    spool_batch(batch, spool_path)
                    logger.error(
                        "spooled_failed_batch records=%s attempts=%s path=%s",
                        len(batch),
                        attempts,
                        spool_path,
                    )
                    break
                time.sleep(retry_interval)
        finally:
            send_queue.task_done()


def main() -> None:
    configure_logging()
    setup_gpio()

    sample_interval = 1.0 / SETTINGS.sample_rate_hz
    try:
        sensor_reader = build_sensor_reader(
            mode=SETTINGS.sensor_mode,
            fault_after_samples=SETTINGS.fault_after_samples,
            settings=SETTINGS,
        )
    except SensorReadError as exc:
        logger.error("sensor_startup_failed %s", exc)
        raise SystemExit(1) from exc
    detector = FaultDetector(
        window_size=SETTINGS.window_size,
        baseline_windows=SETTINGS.baseline_windows,
        reduced_threshold_z=SETTINGS.reduced_threshold_z,
        stop_threshold_z=SETTINGS.stop_threshold_z,
        normal_speed_ratio=SETTINGS.normal_speed_ratio,
        reduced_speed_ratio=SETTINGS.reduced_speed_ratio,
    )
    motor = MotorController(settings=SETTINGS)
    api_client = ApiClient(
        device_id=SETTINGS.device_id,
        endpoint=SETTINGS.api_endpoint,
        enabled=SETTINGS.sender_enabled,
    )

    send_queue: "queue.Queue[list[dict] | object]" = queue.Queue()
    spool_path = Path(SETTINGS.sender_spool_path)
    enqueue_spooled_batches(send_queue, spool_path)
    sender_thread = threading.Thread(
        target=sender_loop,
        args=(
            send_queue,
            api_client,
            SETTINGS.send_retry_interval,
            SETTINGS.send_max_retries,
            spool_path,
        ),
    )
    sender_thread.start()

    buffer: list[dict] = []
    last_send_time = time.monotonic()
    consecutive_sensor_failures = 0

    try:
        while True:
            loop_started = time.monotonic()
            try:
                sample = sensor_reader.read()
                consecutive_sensor_failures = 0
            except Exception:
                consecutive_sensor_failures += 1
                motor.stop()
                logger.exception(
                    "sensor_read_failed consecutive_failures=%s/%s",
                    consecutive_sensor_failures,
                    SETTINGS.max_sensor_failures,
                )
                if consecutive_sensor_failures >= SETTINGS.max_sensor_failures:
                    raise
                time.sleep(sample_interval)
                continue

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
                flush_buffer(buffer, send_queue)
                last_send_time = now

            elapsed = time.monotonic() - loop_started
            if elapsed < sample_interval:
                time.sleep(sample_interval - elapsed)
    finally:
        flush_buffer(buffer, send_queue)
        send_queue.put(SEND_STOP)
        send_queue.join()
        sender_thread.join()
        motor.close()
        sensor_reader.close()


if __name__ == "__main__":
    main()
