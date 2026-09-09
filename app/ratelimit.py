import time
from collections import defaultdict, deque

from .config import settings


class SlidingWindowLimiter:
    """Per-project write budget, in process.

    A page that errors in a loop, or a scanner wired into a hot reload, can post
    continuously. Without a ceiling the database absorbs it and every other project's
    writes queue behind it, so the limit is per project rather than global -- one noisy
    project must not be able to starve the rest.

    In process means it holds for one worker. Run two and the effective limit doubles.
    That is the honest boundary of this implementation and the point at which the
    counter belongs in Redis; see the README.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.monotonic() if now is None else now
        hits = self._hits[key]

        cutoff = now - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self.limit:
            # Tell the caller when the oldest hit falls out of the window, so a retry
            # has a reason to succeed instead of arriving blind.
            return False, max(1, int(hits[0] + self.window - now) + 1)

        hits.append(now)
        return True, 0

    def reset(self) -> None:
        """Drop all counters. Used between tests; there is no runtime caller."""
        self._hits.clear()


limiter = SlidingWindowLimiter(
    settings.rate_limit_requests, settings.rate_limit_window_seconds
)
