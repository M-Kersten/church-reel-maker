"""Minimal in-process background job manager (one job per key)."""

import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Callable


class Cancelled(Exception):
    """Raised inside a job when the user pressed stop."""


@dataclass
class Job:
    status: str = "idle"  # idle | running | done | error | cancelled
    progress: float = 0.0  # 0.0 .. 1.0, as last reported by the work itself
    message: str = ""
    error: str | None = None
    cancelled: bool = False  # set by JobManager.cancel; long steps check this and stop
    # For carrying the bar forward between readings. Some work reports in big steps:
    # batched transcription hands back four minutes of text at a time, so without this
    # the bar would stand still for half a minute and then jump.
    _at: float = field(default_factory=time.monotonic)  # when progress last changed
    _phase_at: float = field(default_factory=time.monotonic)  # when this kind of work started
    _phase_from: float = 0.0  # progress at that moment

    def stop_requested(self) -> bool:
        return self.cancelled

    def check(self) -> None:
        if self.cancelled:
            raise Cancelled

    def start_phase(self) -> None:
        """A different kind of work starts here; measure its speed from this point."""
        self._phase_at = time.monotonic()
        self._phase_from = self.progress

    def advance(self, fraction: float) -> None:
        """Record real progress, and note when it arrived."""
        self.progress = fraction
        self._at = time.monotonic()

    def shown(self) -> float:
        """Progress to display: the last reading, carried on at the speed measured so far."""
        if self.status != "running":
            return self.progress
        now = time.monotonic()
        span, done = now - self._phase_at, self.progress - self._phase_from
        if span <= 0 or done <= 0:
            return self.progress
        return min(0.99, self.progress + (done / span) * (now - self._at))

    def to_dict(self) -> dict:
        fields = {k: v for k, v in asdict(self).items() if k != "cancelled" and not k.startswith("_")}
        return fields | {"progress": round(self.shown(), 4), "canStop": self.status == "running"}


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


def human_remaining(seconds: float) -> str:
    """Time left, in the words someone waiting for it would use."""
    if seconds < 45:
        return "nog geen minuut"
    minutes = int(seconds / 60 + 0.5)  # half a minute rounds up, the way a person would say it
    if minutes <= 1:
        return "nog ongeveer een minuut"
    if minutes < 60:
        return f"nog ongeveer {minutes} minuten"
    hours, rest = divmod(minutes, 60)
    if rest < 8:
        return f"nog ongeveer {hours} uur" if hours > 1 else "nog ongeveer een uur"
    return f"nog ongeveer {hours} uur en {rest} minuten"


class Estimator:
    """How long is left, from how fast the work has actually been going.

    A guess made in the first seconds is worthless and a guess made across two phases that
    run at different speeds is worse, so this ignores progress below `after` and says
    nothing until `settle` seconds of real work have gone by.
    """

    def __init__(self, after: float = 0.0, settle: float = 10.0) -> None:
        self.after = after
        self.settle = settle
        self._started: float | None = None
        self._from: float = after

    def remaining(self, fraction: float) -> float | None:
        if fraction >= 1.0:
            return None
        now = time.monotonic()
        # The reading that opens the phase is the baseline. Work that reports in bursts
        # would otherwise measure its speed across one burst and think it took no time.
        if self._started is None and fraction >= self.after:
            self._started, self._from = now, fraction
        if self._started is None or fraction <= self.after:
            return None
        elapsed = now - self._started
        done = fraction - self._from
        if elapsed < self.settle or done <= 0.001:
            return None
        return elapsed * (1.0 - fraction) / done

    def note(self, fraction: float, message: str) -> str:
        """`message`, with the time left appended once there is something worth saying."""
        left = self.remaining(fraction)
        return f"{message} · {human_remaining(left)}" if left is not None else message
