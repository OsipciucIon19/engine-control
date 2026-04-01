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
    api_endpoint: str = os.getenv("API_ENDPOINT", "")
    device_id: str = os.getenv("DEVICE_ID", "device_001")
    batch_size: int = int(os.getenv("BATCH_SIZE", 100))
    send_interval: float = float(os.getenv("SEND_INTERVAL", 5))
    sample_rate_hz: float = float(os.getenv("SAMPLE_RATE_HZ", 100))
    window_size: int = int(os.getenv("WINDOW_SIZE", 64))
    baseline_windows: int = int(os.getenv("BASELINE_WINDOWS", 10))
    reduced_threshold_z: float = float(os.getenv("REDUCED_THRESHOLD_Z", 2.0))
    stop_threshold_z: float = float(os.getenv("STOP_THRESHOLD_Z", 3.5))
    reduced_clear_threshold_z: float = float(os.getenv("REDUCED_CLEAR_THRESHOLD_Z", 1.8))
    stop_clear_threshold_z: float = float(os.getenv("STOP_CLEAR_THRESHOLD_Z", 3.2))
    reduced_speed_ratio: float = float(os.getenv("REDUCED_SPEED_RATIO", 0.6))
    normal_speed_ratio: float = float(os.getenv("NORMAL_SPEED_RATIO", 1.0))
    z_score_smoothing_windows: int = int(os.getenv("Z_SCORE_SMOOTHING_WINDOWS", 5))
    state_confirmation_windows: int = int(os.getenv("STATE_CONFIRMATION_WINDOWS", 3))
    sensor_mode: str = os.getenv("SENSOR_MODE", "simulated")
    motor_mode: str = os.getenv("MOTOR_MODE", "mock")
    fault_after_samples: int = int(os.getenv("FAULT_AFTER_SAMPLES", 0))
    sender_enabled: bool = _get_bool("SENDER_ENABLED", True)
    send_retry_interval: float = float(os.getenv("SEND_RETRY_INTERVAL", 2))
    send_max_retries: int = int(os.getenv("SEND_MAX_RETRIES", 5))
    sender_spool_path: str = os.getenv("SENDER_SPOOL_PATH", "data/failed_batches.jsonl")
    max_sensor_failures: int = int(os.getenv("MAX_SENSOR_FAILURES", 3))
    i2c_bus: int = int(os.getenv("I2C_BUS", 1))
    adxl345_address: int = int(os.getenv("ADXL345_ADDRESS", "0x53"), 0)
    ads1115_address: int = int(os.getenv("ADS1115_ADDRESS", "0x48"), 0)
    ads1115_channel: int = int(os.getenv("ADS1115_CHANNEL", 0))
    ads1115_gain: float = float(os.getenv("ADS1115_GAIN", "4.096"))
    ads1115_data_rate: int = int(os.getenv("ADS1115_DATA_RATE", 128))
    acs712_zero_voltage: float = float(os.getenv("ACS712_ZERO_VOLTAGE", 2.5))
    acs712_sensitivity: float = float(os.getenv("ACS712_SENSITIVITY", 0.1))
    acs712_voltage_divider_ratio: float = float(os.getenv("ACS712_VOLTAGE_DIVIDER_RATIO", 1.0))
    current_noise_floor_amps: float = float(os.getenv("CURRENT_NOISE_FLOOR_AMPS", 0.0))
    ds18b20_device_path: str = os.getenv(
        "DS18B20_DEVICE_PATH",
        "/sys/bus/w1/devices/28-000000000000/w1_slave",
    )
    motor_forward_pwm_pin: int = int(os.getenv("MOTOR_FORWARD_PWM_PIN", 18))
    motor_reverse_pwm_pin: int = int(os.getenv("MOTOR_REVERSE_PWM_PIN", 19))
    motor_enable_right_pin: int = int(os.getenv("MOTOR_ENABLE_RIGHT_PIN", 23))
    motor_enable_left_pin: int = int(os.getenv("MOTOR_ENABLE_LEFT_PIN", 24))
    motor_pwm_frequency_hz: int = int(os.getenv("MOTOR_PWM_FREQUENCY_HZ", 1000))


SETTINGS = Settings()
