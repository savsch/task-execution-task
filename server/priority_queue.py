import heapq
import threading
from typing import Optional, Tuple
from dataclasses import dataclass
import time

from utils import get_timestamp


@dataclass(order=True)
class PrioritizedTask:
    priority: int
    timestamp: int
    task_id: str = None  # Will be compared by priority and timestamp only

class CancellablePriorityQueue:
    def __init__(self):
        self._queue = []
        self._lock = threading.Lock()
        self._cancelled = set()
        self._task_set = set()  # Track active tasks for fast lookup

    def put(self, task_id: str, priority: int) -> None:
        with self._lock:
            if task_id not in self._cancelled and task_id not in self._task_set:
                heapq.heappush(
                    self._queue,
                    PrioritizedTask(priority, get_timestamp(), task_id)
                )
                self._task_set.add(task_id)

    def get(self) -> Optional[int]:
        with self._lock:
            while self._queue:
                task = heapq.heappop(self._queue)
                if task.task_id not in self._cancelled:
                    self._task_set.remove(task.task_id)  # Remove from task set when returned
                    return task.task_id
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