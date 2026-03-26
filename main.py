import time
import threading
from config import DEVICE_ID, BATCH_SIZE, SEND_INTERVAL
from hardware.sensors import read_sensor
from hardware.motor import set_motor_speed
from core.schur import run_schur
from services.api_client import ApiClient
from queue import Queue
from datetime import datetime

api_client = ApiClient(device_id=DEVICE_ID)

buffer = []
queue = Queue()

def collect(sensor, result, motor):
    return {
        "timestamp": datetime.now().isoformat(),
        "sensor": {
            "value": sensor
        },
        "algorithm": {"result": result},
        "motor": {
            "speed": motor,
            "state": "active" if motor > 0 else "inactive"
        }
    }

def sender():
    while True:
        batch = queue.get()
        api_client.send_batch(batch)
        queue.task_done()

threading.Thread(target=sender, daemon=True).start()

def main():
    global buffer
    last_send_time = time.time()

    while True:
        data = read_sensor()
        result = run_schur(data)
        set_motor_speed(result)

        buffer.append(collect(data, result, result))

        now = time.time()

        if len(buffer) >= BATCH_SIZE or (now - last_send_time) >= SEND_INTERVAL:
            queue.put(buffer.copy())
            buffer.clear()
            last_send_time = now

        time.sleep(0.5)

if __name__ == "__main__":
    main()
    