import threading
import os
from typing import Optional, Dict, Type
import json
from pathlib import Path
import time

from running_tasks import RunningTasks
from task_interfaces import TaskOutput, TaskType, TaskParams, StatusUpdate
from task_executor import TaskExecutor, EchoTaskExecutor
from db_manager import DatabaseManager
from priority_queue import CancellablePriorityQueue
from utils import get_timestamp


class WorkerThread(threading.Thread):
    def __init__(
        self,
        queue: CancellablePriorityQueue,
        db: DatabaseManager,
        reports_dir: str,
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
            task_id = self.queue.get()
            if task_id is None:
                time.sleep(0.1)
                continue

            self.execute_task(task_id)

    def execute_task(self, task_id: str):
        self.running_tasks.add(task_id)
        try:
            report_path = Path(self.reports_dir) / str(task_id)
            report_path.mkdir(parents=True, exist_ok=True)
            output_file = report_path / "output.txt"

            # Set the report path in database before starting execution
            self.db.set_report_path(task_id, str(output_file.resolve()))

            class TaskOutputHandler(TaskOutput):
                def __init__(self, status_callback, task_id: str, output_file: Path):
                    self.status_callback = status_callback
                    self.task_id = task_id
                    self.output_file = output_file
                    self.exit_code: Optional[int] = None

                def emit_normal_output(self, data: str):
                    with open(self.output_file, "a") as f:
                        f.write(f"{data}\n")
                    self.status_callback(
                        self.task_id,
                        StatusUpdate(timestamp=get_timestamp(), stdout=data)
                    )

                def emit_error_output(self, data: str):
                    with open(self.output_file, "a") as f:
                        f.write(f"STDERR: {data}\n")
                    self.status_callback(
                        self.task_id,
                        StatusUpdate(timestamp=get_timestamp(), stderr=data)
                    )

                def set_exit_code(self, code: int):
                    self.exit_code = code
                    with open(self.output_file, "a") as f:
                        f.write(f"\nPROCESS EXITED WITH EXIT CODE: {code}\n")

            output_handler = TaskOutputHandler(self.status_callback, task_id, output_file)

            params = TaskParams(type=TaskType.ECHO, args=["test"])
            executor = EchoTaskExecutor(task_id, params, output_handler)

            self.db.update_task_start(task_id)
            exit_code = executor.execute(timeout=self.timeout)
            self.db.update_task_end(task_id)

            self.status_callback(
                task_id,
                "SUCCESS" if exit_code == 0 else {"error": f"Task failed with exit code {exit_code}"}
            )
        finally:
            self.running_tasks.remove(task_id)