import json
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class _FakeApiClient:
    def __init__(self, results: list[str]) -> None:
        self.results = results
        self.calls = 0

    def send_batch(self, batch: list[dict]) -> str:
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return "sent"


class RuntimeTests(unittest.TestCase):
    def test_sender_loop_spools_batch_after_retry_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spool_path = Path(temp_dir) / "failed_batches.jsonl"
            send_queue: "queue.Queue[list[dict] | object]" = queue.Queue()
            send_queue.put([{"value": 1}])
            send_queue.put(main.SEND_STOP)
            api_client = _FakeApiClient(["retry", "retry"])

            with patch("main.time.sleep", return_value=None):
                main.sender_loop(send_queue, api_client, retry_interval=0, max_retries=2, spool_path=spool_path)

            self.assertEqual(api_client.calls, 2)
            self.assertTrue(spool_path.exists())
            lines = spool_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0]), [{"value": 1}])

    def test_enqueue_spooled_batches_queues_saved_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spool_path = Path(temp_dir) / "failed_batches.jsonl"
            spool_path.write_text(json.dumps([{"value": 1}]) + "\n", encoding="utf-8")
            send_queue: "queue.Queue[list[dict] | object]" = queue.Queue()

            main.enqueue_spooled_batches(send_queue, spool_path)

            self.assertEqual(send_queue.get_nowait(), [{"value": 1}])
            self.assertFalse(spool_path.exists())

    def test_enqueue_spooled_batches_recovers_pending_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spool_path = Path(temp_dir) / "failed_batches.jsonl"
            pending_path = spool_path.with_suffix(".jsonl.pending")
            pending_path.write_text(json.dumps([{"value": 2}]) + "\n", encoding="utf-8")
            send_queue: "queue.Queue[list[dict] | object]" = queue.Queue()

            main.enqueue_spooled_batches(send_queue, spool_path)

            self.assertEqual(send_queue.get_nowait(), [{"value": 2}])
            self.assertFalse(pending_path.exists())


if __name__ == "__main__":
    unittest.main()
