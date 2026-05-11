import json
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from openai import OpenAI

from .config import PipelineConfig


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


class BatchRunner:
    def __init__(self, api_key: str, config: PipelineConfig):
        self.client = OpenAI(api_key=api_key)
        self.config = config

    def upload_batch_file(self, jsonl_path: str) -> str:
        with open(jsonl_path, "rb") as f:
            file_obj = self.client.files.create(file=f, purpose="batch")
        return file_obj.id

    def create_batch(self, input_file_id: str) -> str:
        batch = self.client.batches.create(
            input_file_id=input_file_id,
            endpoint=self.config.endpoint,
            completion_window=self.config.completion_window,
        )
        return batch.id

    def wait_for_completion(self, batch_id: str) -> Dict:
        max_wait_s = self.config.max_wait_minutes * 60
        elapsed = 0
        last_status_logged = ""
        last_progress_log_s = 0
        while elapsed <= max_wait_s:
            batch = self.client.batches.retrieve(batch_id)
            status = batch.status
            counts = getattr(batch, "request_counts", None)
            if counts is not None:
                completed = getattr(counts, "completed", 0) or 0
                failed = getattr(counts, "failed", 0) or 0
                total = getattr(counts, "total", 0) or 0
            else:
                completed, failed, total = 0, 0, 0

            if status != last_status_logged:
                _log(f"  batch {batch_id} status={status} ({completed}/{total} done, {failed} failed, elapsed={elapsed}s)")
                last_status_logged = status
                last_progress_log_s = elapsed
            elif elapsed - last_progress_log_s >= 300:
                _log(f"  batch {batch_id} still {status} ({completed}/{total} done, {failed} failed, elapsed={elapsed}s)")
                last_progress_log_s = elapsed

            if status in {"completed", "failed", "cancelled", "expired"}:
                return batch.model_dump()
            time.sleep(self.config.poll_interval_seconds)
            elapsed += self.config.poll_interval_seconds
        raise TimeoutError(f"Batch {batch_id} timed out after {self.config.max_wait_minutes} minutes.")

    def download_file_content(self, file_id: str, output_path: str) -> None:
        content = self.client.files.content(file_id)
        with open(output_path, "wb") as f:
            f.write(content.read())


def extract_file_ids(batch_data: Dict) -> Dict[str, Optional[str]]:
    return {
        "output_file_id": batch_data.get("output_file_id"),
        "error_file_id": batch_data.get("error_file_id"),
    }


def save_batch_metadata(batch_data: Dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(batch_data, f, ensure_ascii=True, indent=2)

