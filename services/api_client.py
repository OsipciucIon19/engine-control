import requests
import json

from config import API_ENDPOINT

class ApiClient:
    def __init__(self, device_id, endpoint=API_ENDPOINT):
        self.device_id = device_id
        self.endpoint = endpoint
    

    def send_batch(self, batch):
        payload = {
            "device_id": self.device_id,
            "batch": batch
        }
        
        try:
            print("Sending data batch to API...", payload, self.endpoint)
            response = requests.post(self.endpoint, json=payload, timeout=5)
            response.raise_for_status()
            print("Data sent successfully", response.text)
        except requests.exceptions.RequestException as e:
            print(f"Failed to send data: {e}")