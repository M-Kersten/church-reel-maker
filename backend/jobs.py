"""Minimal in-process background job manager (one job per key)."""

import threading
import traceback
from dataclasses import asdict, dataclass
from typing import Callable


class Cancelled(Exception):
    """Raised inside a job when the user pressed stop."""


@dataclass
class Job:
    status: str = "idle"  # idle | running | done | error | cancelled
    progress: float = 0.0  # 0.0 .. 1.0
    message: str = ""
    error: str | None = None
    cancelled: bool = False  # set by JobManager.cancel; long steps check this and stop

    def stop_requested(self) -> bool:
        return self.cancelled

    def check(self) -> None:
        if self.cancelled:
            raise Cancelled

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "cancelled"} | {"canStop": self.status == "running"}


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Job:
        with self._lock:
            return self._jobs.get(key, Job())

    def is_running(self, key: str) -> bool:
        return self.get(key).status == "running"

    def cancel(self, key: str) -> bool:
        """Ask a running job to stop. It ends at its next checkpoint."""
        job = self.get(key)
        if job.status != "running":
            return False
        job.cancelled = True
        job.message = "Bezig met stoppen…"
        return True

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
            except Cancelled:
                job.status = "cancelled"
                job.message = "Gestopt"
            except Exception as exc:  # noqa: BLE001
                job.status = "error"
                job.error = str(exc)
                job.message = "Mislukt"
                traceback.print_exc()

        threading.Thread(target=run, name=f"job-{key}", daemon=True).start()
        return job
