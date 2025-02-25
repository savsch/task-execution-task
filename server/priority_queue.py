import heapq
import threading
from typing import Optional
from dataclasses import dataclass

from utils import get_timestamp


@dataclass(order=True)
class PrioritizedTask:
    minus_priority: int    # The higher the priority (lower the minus_priority), the earlier it's executed
    timestamp: int         # The lower the timestamp, the earlier it's executed
    task_id: str
    params: dict           # This needs to come after only task_id as we never intend to compare via params only to end up in a TypeError

class CancellablePriorityQueue:
    def __init__(self):
        self._queue = []
        self._lock = threading.Lock()
        self._cancelled = set()
        self._task_set = set()

    def put(self, task_id: str, priority: int, params: dict) -> None:
        with self._lock:
            if task_id not in self._cancelled and task_id not in self._task_set:
                heapq.heappush(
                    self._queue,
                    PrioritizedTask(-priority, get_timestamp(), task_id, params)
                )
                self._task_set.add(task_id)

    def get(self) -> Optional[PrioritizedTask]:
        with self._lock:
            while self._queue:
                task = heapq.heappop(self._queue)
                if task.task_id not in self._cancelled:
                    self._task_set.remove(task.task_id)
                    return task
            return None

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._task_set:
                self._cancelled.add(task_id)
                self._task_set.remove(task_id)
                return True
            return False

    def is_task_enqueued(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._task_set