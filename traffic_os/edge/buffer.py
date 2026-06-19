"""Edge store-and-forward buffer — resilient uplink across connectivity gaps."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from traffic_os.common.logging import get_logger
from traffic_os.schemas import CameraFrameMetric

log = get_logger("edge.buffer")


class EdgeBuffer:
    """Buffers metrics while offline and flushes them in order once online."""

    def __init__(self, sink: Callable[[CameraFrameMetric], None], *, maxlen: int = 5000) -> None:
        self.sink = sink
        self.online = True
        self._queue: deque[CameraFrameMetric] = deque(maxlen=maxlen)
        self.dropped = 0

    def record(self, metric: CameraFrameMetric) -> None:
        if self.online:
            self.sink(metric)
            return
        if len(self._queue) == self._queue.maxlen:
            self.dropped += 1
        self._queue.append(metric)

    def set_online(self, online: bool) -> int:
        """Toggle connectivity. On reconnect, flush the buffer; return #flushed."""
        self.online = online
        flushed = 0
        if online:
            while self._queue:
                self.sink(self._queue.popleft())
                flushed += 1
            if flushed:
                log.info("Edge reconnected: flushed %d buffered metrics", flushed)
        return flushed

    @property
    def pending(self) -> int:
        return len(self._queue)
