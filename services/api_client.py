from __future__ import annotations

import logging
from typing import Literal
from typing import Any, Sequence

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    requests = None


SendBatchResult = Literal["sent", "retry", "skipped"]


class ApiClient:
    def __init__(self, device_id: str, endpoint: str, enabled: bool = True) -> None:
        self.device_id = device_id
        self.endpoint = endpoint
        self.enabled = enabled and bool(endpoint)
        self.logger = logging.getLogger(__name__)

    def send_batch(self, batch: Sequence[dict[str, Any]]) -> SendBatchResult:
        if not batch:
            return "sent"

        if not self.enabled:
            self.logger.info("Skipping batch send because API delivery is disabled")
            return "skipped"
        if requests is None:
            self.logger.warning("Skipping batch send because requests is not installed")
            return "skipped"

        payload = {"device_id": self.device_id, "batch": list(batch)}
        try:
            response = requests.post(self.endpoint, json=payload, timeout=5)
            response.raise_for_status()
            self.logger.info("Sent batch with %s records", len(batch))
            return "sent"
        except requests.RequestException as exc:
            self.logger.warning("Failed to send batch: %s", exc)
            return "retry"
