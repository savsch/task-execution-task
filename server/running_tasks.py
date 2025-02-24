# A thread safe, singleton set, which will be maintained by the worker threads, which just has the taskid's of running tasks
import threading

class RunningTasks:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RunningTasks, cls).__new__(cls)
                cls._instance._tasks = set()
                cls._instance._set_lock = threading.Lock()
            return cls._instance

    def add(self, task_id: str):
        with self._set_lock:
            self._tasks.add(task_id)

    def remove(self, task_id: str):
        with self._set_lock:
            self._tasks.discard(task_id)

    def is_running(self, task_id: str) -> bool:
        with self._set_lock:
            return task_id in self._tasks