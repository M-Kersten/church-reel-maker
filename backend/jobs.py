"""Minimal in-process background job manager (one job per key)."""

import threading
import traceback
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass
class Job:
    status: str = "idle"  # idle | running | done | error
    progress: float = 0.0  # 0.0 .. 1.0
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Job:
        with self._lock:
            return self._jobs.get(key, Job())

    def is_running(self, key: str) -> bool:
        return self.get(key).status == "running"

    def start(self, key: str, work: Callable[[Job], None]) -> Job:
        """Run `work(job)` in a daemon thread. `work` updates job.progress/message."""
        with self._lock:
            if self._jobs.get(key, Job()).status == "running":
                raise RuntimeError("job already running")
            job = Job(status="running", message="Bezig met starten")
            self._jobs[key] = job

        def run() -> None:
            try:
                work(job)
                job.progress = 1.0
                job.status = "done"
                job.message = "Klaar"
            except Exception as exc:  # noqa: BLE001
                job.status = "error"
                job.error = str(exc)
                job.message = "Mislukt"
                traceback.print_exc()

        threading.Thread(target=run, name=f"job-{key}", daemon=True).start()
        return job
