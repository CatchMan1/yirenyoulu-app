"""Serial pacing and hard transfer ceilings for local operator downloads."""

import time


class DownloadBudget:
    def __init__(self, max_requests=300, max_bytes=128 * 1024 * 1024, interval=2):
        self.max_requests = max_requests
        self.max_bytes = max_bytes
        self.interval = interval
        self.requests = 0
        self.bytes = 0
        self.last = None

    def request(self):
        if self.requests >= self.max_requests:
            raise ValueError("REQUEST_BUDGET")
        if self.last is not None:
            time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        self.requests += 1

    def received(self, size):
        if size < 0 or self.bytes + size > self.max_bytes:
            raise ValueError("BYTE_BUDGET")
        self.bytes += size
