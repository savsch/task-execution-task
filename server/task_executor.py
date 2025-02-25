import subprocess
from typing import Optional
import threading
from abc import ABC
from task_interfaces import TaskOutput

class TaskExecutor(ABC):
    def __init__(self, task_id: str, request_args, output_handler: TaskOutput):
        self.task_id = task_id
        self.request_args = request_args
        self.output_handler = output_handler
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()
        if self._process:
            self._process.terminate()

    def execute(self, timeout: Optional[float] = None) -> int:
        raise NotImplementedError

    @classmethod
    def validate(cls, request_args):
        """
        Must raise TaskValidationException if validation fails.
        This will be called on the Stellar loop, so should be lightweight.
        """
        pass