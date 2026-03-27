# Engine Control

Real-time motor fault detection prototype for Raspberry Pi using a Schur-decomposition-based health indicator.

The current implementation supports both simulation and a real hardware path for:

- Raspberry Pi 5
- MY6812 12 VDC 150 W brushed motor
- BTS7960B motor driver
- ADXL345 accelerometer
- ADS1115 ADC
- ACS712 current sensor
- DS18B20 temperature probe

It includes:

- 5-channel sensor sampling: vibration X/Y/Z, current, temperature
- Sliding-window covariance analysis
- Pure-Python Schur decomposition
- Z-score fault detection against a learned baseline
- Motor state transitions: `normal`, `reduced`, `stop`
- Buffered API batch delivery

## Status

The signal-processing and control pipeline is implemented.

Supported runtime modes:

- `SENSOR_MODE=simulated` uses synthetic sensor values for development
- `SENSOR_MODE=real` reads `ADXL345`, `ADS1115 + ACS712`, and `DS18B20`
- `MOTOR_MODE=mock` keeps motor commands in memory
- `MOTOR_MODE=real` drives the `BTS7960` with Raspberry Pi PWM and enable pins

The runtime stops the motor on repeated sensor read failures and disables the driver on shutdown.

## Project Structure

```text
.
├── config.py                Runtime configuration from environment variables
├── main.py                  Main acquisition, detection, control, and batching loop
├── core/
│   ├── processing.py        Sliding window, covariance, Z-score, state machine
│   └── schur.py             Pure-Python QR/Schur implementation
├── hardware/
│   ├── gpio_setup.py        GPIO setup hook
│   ├── motor.py             Mock and BTS7960-backed motor controllers
│   └── sensors.py           Simulated and real sensor readers
├── services/
│   └── api_client.py        Optional HTTP batch sender
├── tests/
│   └── test_schur.py        Unit tests for Schur math and fault detection
└── docs/
    └── IMPLEMENTATION_PLAN.md
```

## How It Works

The runtime pipeline is:

```text
sensor sample
-> sliding window
-> covariance matrix
-> Schur decomposition
-> health index
-> Z-score
-> motor state machine
-> API batch payload
```

Each sample contains:

```python
[vib_x, vib_y, vib_z, current, temperature]
```

For each full window:

1. A covariance matrix is computed from the recent samples.
2. The covariance matrix is transformed with Schur decomposition.
3. The dominant Schur diagonal term is used as the health index.
4. The health index is compared to a baseline using a Z-score.
5. The motor state machine decides whether the motor remains `normal`, drops to `reduced`, or goes to `stop`.

## Requirements

- Python 3.13
- Optional Python packages from `requirements.txt`

Real hardware mode also needs:

- `smbus2` for I2C sensor access
- `gpiozero` for PWM and GPIO output
- Raspberry Pi `I2C` and `1-Wire` interfaces enabled

## Setup

If you already have a virtual environment in `venv`, activate it or use it directly.

Install dependencies:

```bash
./venv/bin/pip install -r requirements.txt
```

Create a local environment file:

```bash
cp .env.example .env
```

## Run

Run from the repository root:

```bash
./venv/bin/python main.py
```

Run with a simulated fault injected after 120 samples:

```bash
FAULT_AFTER_SAMPLES=120 ./venv/bin/python main.py
```

Run against real hardware:

```bash
SENSOR_MODE=real MOTOR_MODE=real ./venv/bin/python main.py
```

## Configuration

Environment variables are loaded from `.env` when `python-dotenv` is available.

| Variable | Default | Description |
| --- | --- | --- |
| `API_ENDPOINT` | empty | HTTP endpoint for batch delivery |
| `DEVICE_ID` | `device_001` | Device identifier sent with batches |
| `BATCH_SIZE` | `10` | Number of records per outgoing batch |
| `SEND_INTERVAL` | `5` | Max seconds before a partial batch is sent |
| `SAMPLE_RATE_HZ` | `100` | Sampling frequency |
| `WINDOW_SIZE` | `64` | Sliding-window size used for covariance |
| `BASELINE_WINDOWS` | `10` | Number of windows collected before Z-score activation |
| `REDUCED_THRESHOLD_Z` | `2.0` | Z-score threshold for reduced mode |
| `STOP_THRESHOLD_Z` | `3.5` | Z-score threshold for stop mode |
| `REDUCED_SPEED_RATIO` | `0.6` | Motor speed ratio in reduced mode |
| `NORMAL_SPEED_RATIO` | `1.0` | Motor speed ratio in normal mode |
| `SENSOR_MODE` | `simulated` | `simulated` or `real` sensor backend |
| `MOTOR_MODE` | `mock` | `mock` or `real` motor backend |
| `FAULT_AFTER_SAMPLES` | `0` | Injects a simulated fault after N samples; `0` disables fault injection |
| `SENDER_ENABLED` | `true` | Enables API batch delivery |
| `SEND_RETRY_INTERVAL` | `2` | Seconds between HTTP retry attempts |
| `SEND_MAX_RETRIES` | `5` | Retries before a batch is spooled locally |
| `SENDER_SPOOL_PATH` | `data/failed_batches.jsonl` | Local JSONL spool for undelivered batches |
| `MAX_SENSOR_FAILURES` | `3` | Consecutive read failures before exit |
| `I2C_BUS` | `1` | Linux I2C bus number |
| `ADXL345_ADDRESS` | `0x53` | ADXL345 I2C address |
| `ADS1115_ADDRESS` | `0x48` | ADS1115 I2C address |
| `ADS1115_CHANNEL` | `0` | ADS1115 single-ended channel used for ACS712 |
| `ADS1115_GAIN` | `4.096` | ADS1115 full-scale range in volts |
| `ADS1115_DATA_RATE` | `128` | ADS1115 samples per second |
| `ACS712_ZERO_VOLTAGE` | `2.5` | Zero-current ACS712 output in volts |
| `ACS712_SENSITIVITY` | `0.1` | Volts per amp for ACS712 20A |
| `ACS712_VOLTAGE_DIVIDER_RATIO` | `1.0` | Multiplier to reconstruct sensor voltage after a divider |
| `CURRENT_NOISE_FLOOR_AMPS` | `0.05` | Clamp small current noise to zero |
| `DS18B20_DEVICE_PATH` | `/sys/bus/w1/devices/.../w1_slave` | DS18B20 sysfs path |
| `MOTOR_FORWARD_PWM_PIN` | `18` | BTS7960 `RPWM` pin |
| `MOTOR_REVERSE_PWM_PIN` | `19` | BTS7960 `LPWM` pin |
| `MOTOR_ENABLE_RIGHT_PIN` | `23` | BTS7960 `R_EN` pin |
| `MOTOR_ENABLE_LEFT_PIN` | `24` | BTS7960 `L_EN` pin |
| `MOTOR_PWM_FREQUENCY_HZ` | `1000` | PWM carrier frequency |

## Logging

The app logs computed runtime values such as:

- `health_index`
- `z_score`
- detected `state`
- applied `speed_ratio`
- whether the baseline is ready

This makes it easy to observe when the simulated system transitions from healthy to degraded operation.

During startup, the motor remains stopped until the baseline window is fully learned. If HTTP delivery fails repeatedly, the batch is retried and then written to the local spool path instead of being dropped.

## Wiring Notes

- `ADXL345` and `ADS1115` share the Pi I2C bus on `GPIO2/GPIO3`.
- `DS18B20` should be on `GPIO4` with a `4.7 kOhm` pull-up to `3.3 V`.
- The default `BTS7960` mapping is `GPIO18 -> RPWM`, `GPIO19 -> LPWM`, `GPIO23 -> R_EN`, `GPIO24 -> L_EN`.
- The current code drives forward only and keeps reverse PWM low.
- `ACS712` calibration is installation-specific. Set `ACS712_ZERO_VOLTAGE` after measuring the zero-current output.
- If you scale the `ACS712` output with a voltage divider before the `ADS1115`, set `ACS712_VOLTAGE_DIVIDER_RATIO` to match that divider.

## Testing

Run the test suite with:

```bash
./venv/bin/python -m unittest discover -s tests -v
```

The tests cover:

- Schur decomposition convergence on a symmetric matrix
- Health-index extraction
- Covariance-matrix symmetry
- Fault-detector transition into `stop`

## Notes

- The current health index is the dominant diagonal value of the Schur triangular matrix derived from the covariance matrix.
- The baseline is learned online from the first configured number of windows.
- If the baseline variance is effectively zero and the health index increases, the detector treats that as an extreme anomaly.

## Next Steps

Typical follow-up work for a real deployment:

- Calibrate `ACS712_ZERO_VOLTAGE` at zero load
- Add replay tooling for locally spooled failed batches if you want an operator-driven recovery workflow
- Add graceful shutdown and signal handling
- Add integration tests around the full runtime loop
