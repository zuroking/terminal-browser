from threading import Lock
from time import monotonic, time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now_monotonic(self) -> float: ...

    def now_epoch(self) -> float: ...


class SystemClock:
    def now_monotonic(self) -> float:
        return monotonic()

    def now_epoch(self) -> float:
        return time()


class FakeClock:
    def __init__(self, monotonic_start: float, epoch_start: float) -> None:
        self._monotonic = monotonic_start
        self._epoch = epoch_start
        self._lock = Lock()

    def now_monotonic(self) -> float:
        with self._lock:
            return self._monotonic

    def now_epoch(self) -> float:
        with self._lock:
            return self._epoch

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        with self._lock:
            self._monotonic += seconds
            self._epoch += seconds

    def set_epoch(self, epoch: float) -> None:
        with self._lock:
            self._epoch = epoch
