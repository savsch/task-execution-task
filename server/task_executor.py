import subprocess
from typing import Optional
import threading
from abc import ABC
from task_interfaces import TaskOutput, TaskType, TaskParams

class TaskExecutor(ABC):
    def __init__(self, task_id: str, params: TaskParams, output_handler: TaskOutput):
        self.task_id = task_id
        self.params = params
        self.output_handler = output_handler
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()
        if self._process:
            self._process.terminate()

    def execute(self, timeout: Optional[float] = None) -> int:
        raise NotImplementedError

class EchoTaskExecutor(TaskExecutor):
    def execute(self, timeout: Optional[float] = None) -> int:
        if not self.params.args or len(self.params.args) != 1:
            self.output_handler.emit_error_output("Echo task requires exactly one argument")
            return 1

        try:
            self._process = subprocess.Popen(
                ['echo', self.params.args[0]],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = self._process.communicate(timeout=timeout)
            
            if stdout:
                self.output_handler.emit_normal_output(stdout)
            if stderr:
                self.output_handler.emit_error_output(stderr)

            exit_code = self._process.returncode
            # self.output_handler.set_exit_code(exit_code)
            return exit_code

        except subprocess.TimeoutExpired:
            self.stop()
            self.output_handler.emit_error_output("Task execution timed out")
            return 1
        except Exception as e:
            self.output_handler.emit_error_output(f"Task execution failed: {str(e)}")
            return 1