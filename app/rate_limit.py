"""Global monotonic upstream limiter and circuit breaker."""

from __future__ import annotations

import math
import time
from collections.abc import Callable


class UpstreamGate:
    def __init__(
        self,
        interval_seconds: float = 65.0,
        failure_threshold: int = 3,
        cooldown_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self.last_request_at: float | None = None
        self.failures = 0
        self.circuit_opened_at: float | None = None

    def wait_seconds(self) -> int:
        now = self.clock()
        if self.circuit_opened_at is not None:
            remaining = self.cooldown_seconds - (now - self.circuit_opened_at)
            if remaining > 0:
                return max(1, math.ceil(remaining))
            self.circuit_opened_at = None
            self.failures = 0
        if self.last_request_at is None:
            return 0
        return max(0, math.ceil(self.interval_seconds - (now - self.last_request_at)))

    def mark_attempt(self) -> None:
        self.last_request_at = self.clock()

    def mark_success(self) -> None:
        self.failures = 0
        self.circuit_opened_at = None

    def mark_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.circuit_opened_at = self.clock()
