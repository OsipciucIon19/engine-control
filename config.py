import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    motor_pin: int = int(os.getenv("MOTOR_PIN", 18))
    sensor_pin: int = int(os.getenv("SENSOR_PIN", 17))
    api_endpoint: str = os.getenv("API_ENDPOINT", "")
    device_id: str = os.getenv("DEVICE_ID", "device_001")
    batch_size: int = int(os.getenv("BATCH_SIZE", 500))
    send_interval: float = float(os.getenv("SEND_INTERVAL", 5))
    sample_rate_hz: float = float(os.getenv("SAMPLE_RATE_HZ", 100))
    window_size: int = int(os.getenv("WINDOW_SIZE", 64))
    baseline_windows: int = int(os.getenv("BASELINE_WINDOWS", 10))
    reduced_threshold_z: float = float(os.getenv("REDUCED_THRESHOLD_Z", 2.0))
    stop_threshold_z: float = float(os.getenv("STOP_THRESHOLD_Z", 3.5))
    reduced_speed_ratio: float = float(os.getenv("REDUCED_SPEED_RATIO", 0.6))
    normal_speed_ratio: float = float(os.getenv("NORMAL_SPEED_RATIO", 1.0))
    sensor_mode: str = os.getenv("SENSOR_MODE", "simulated")
    fault_after_samples: int = int(os.getenv("FAULT_AFTER_SAMPLES", 0))
    sender_enabled: bool = _get_bool("SENDER_ENABLED", True)


SETTINGS = Settings()
