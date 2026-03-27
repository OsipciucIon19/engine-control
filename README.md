# Engine Control

Real-time motor fault detection prototype for Raspberry Pi using a Schur-decomposition-based health indicator.

The current implementation runs end to end with a simulated sensor source and includes:

- 5-channel sensor sampling: vibration X/Y/Z, current, temperature
- Sliding-window covariance analysis
- Pure-Python Schur decomposition
- Z-score fault detection against a learned baseline
- Motor state transitions: `normal`, `reduced`, `stop`
- Buffered API batch delivery

## Status

The signal-processing and control pipeline is implemented.

The hardware layer is still simulation-first:

- Sensor input is simulated
- GPIO setup is a stub
- Motor control is represented as an in-memory command, not real PWM output

If you want to deploy this on a real Raspberry Pi motor rig, the next step is wiring `hardware/sensors.py`, `hardware/motor.py`, and `hardware/gpio_setup.py` to actual devices.

## Project Structure

```text
.
├── config.py                Runtime configuration from environment variables
├── main.py                  Main acquisition, detection, control, and batching loop
├── core/
│   ├── processing.py        Sliding window, covariance, Z-score, state machine
│   └── schur.py             Pure-Python QR/Schur implementation
├── hardware/
│   ├── gpio_setup.py        Raspberry Pi GPIO hook point
│   ├── motor.py             Motor controller abstraction
│   └── sensors.py           Simulated sensor reader and sensor factory
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

The code tolerates missing optional dependencies:

- If `python-dotenv` is not installed, `.env` loading is skipped.
- If `requests` is not installed, API delivery is skipped.

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

## Configuration

Environment variables are loaded from `.env` when `python-dotenv` is available.

| Variable | Default | Description |
| --- | --- | --- |
| `MOTOR_PIN` | `18` | Reserved GPIO pin for motor control |
| `SENSOR_PIN` | `17` | Reserved GPIO pin for sensor hookup |
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
| `SENSOR_MODE` | `simulated` | Current sensor backend |
| `FAULT_AFTER_SAMPLES` | `0` | Injects a simulated fault after N samples; `0` disables fault injection |
| `SENDER_ENABLED` | `true` | Enables API batch delivery |

## Logging

The app logs computed runtime values such as:

- `health_index`
- `z_score`
- detected `state`
- applied `speed_ratio`
- whether the baseline is ready

This makes it easy to observe when the simulated system transitions from healthy to degraded operation.

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

- Add real IMU, current, and temperature sensor drivers
- Replace the motor stub with actual PWM/GPIO control
- Persist failed API batches for retry
- Add graceful shutdown and signal handling
- Add integration tests around the full runtime loop
