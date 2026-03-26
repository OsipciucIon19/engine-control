import os

from dotenv import load_dotenv

load_dotenv()

MOTOR_PIN = int(os.getenv("MOTOR_PIN", 18))
SENSOR_PIN = int(os.getenv("SENSOR_PIN", 17))
API_ENDPOINT = os.getenv("API_ENDPOINT", "http://192.168.1.17:3000/api/data")
DEVICE_ID = os.getenv("DEVICE_ID", "device_001")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 10))
SEND_INTERVAL = int(os.getenv("SEND_INTERVAL", 5))
