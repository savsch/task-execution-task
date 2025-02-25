import threading
import os
from typing import Optional, Dict, Type
import json
from pathlib import Path
import time

from running_tasks import RunningTasks
from task_executors.utils.taskutils import get_task_executor_from_params
from task_interfaces import TaskOutput
from task_executors.echo_executor import EchoTaskExecutor
from db_manager import DatabaseManager
from priority_queue import CancellablePriorityQueue, PrioritizedTask
from utils import get_timestamp, bytes_to_string


class WorkerThread(threading.Thread):
    def __init__(
        self,
        queue: CancellablePriorityQueue,
        db: DatabaseManager,
        reports_dir,
        timeout: float,
        status_callback
    ):
        super().__init__()
        self.queue = queue
        self.db = db
        self.reports_dir = reports_dir
        self.timeout = timeout
        self.status_callback = status_callback
        self.daemon = True
        self._stop_event = threading.Event()
        self.running_tasks = RunningTasks()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            task = self.queue.get()
            if task is None:
                time.sleep(0.1)
                continue

            self.execute_task(task)

    def execute_task(self, task: PrioritizedTask):
        self.running_tasks.add(task.task_id)
        try:
            report_path = Path(self.reports_dir) / str(task.task_id)
            report_path.mkdir(parents=True, exist_ok=True)
            output_file = report_path / "output.txt"

            # Set the report path in database before starting execution
            self.db.set_report_path(task.task_id, str(output_file.resolve()))

            class TaskOutputHandler(TaskOutput):
                def __init__(self, status_callback, task_id: str, output_file: Path):
                    self.status_callback = status_callback
                    self.task_id = task_id
                    self.output_file = output_file
                    self.exit_code: Optional[int] = None

                def emit_normal_output(self, data: bytes):
                    with open(self.output_file, "ab") as f:
                        f.write(data)
                    self.status_callback(
                        self.task_id,
                        status = {"time":get_timestamp(), "stdout": bytes_to_string(data)}
                    )

                def emit_error_output(self, data: bytes):
                    with open(self.output_file, "a") as f:
                        f.write(f"[STDERR: {data}]")
                    self.status_callback(
                        self.task_id,
                        status = {"time":get_timestamp(), "stderr": bytes_to_string(data)}
                    )

                # def set_exit_code(self, code: int):
                #     self.exit_code = code
                #     with open(self.output_file, "a") as f:
                #         f.write(f"\nPROCESS EXITED WITH EXIT CODE: {code}\n")

            output_handler = TaskOutputHandler(self.status_callback, task.task_id, output_file)

            executor_class = get_task_executor_from_params(task.params)
            executor = executor_class(task.task_id, task.params.get("args"), output_handler)

            self.db.update_task_start(task.task_id)
            exit_code = executor.execute(timeout=self.timeout)
            self.db.update_task_end(task.task_id)

            self.status_callback(
                task.task_id, exit_code=exit_code, report_path=str(output_file.resolve())
            )
        finally:
            self.running_tasks.remove(task.task_id)