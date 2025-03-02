import asyncio
import json
import threading
import argparse
import traceback
from pathlib import Path
from typing import Dict
import os

import globalconfig
from running_tasks import RunningTasks
from db_manager import DatabaseManager
from priority_queue import CancellablePriorityQueue
from task_executors.utils.taskutils import validate_params
from task_executors.utils.exceptions import TaskValidationException
from worker import WorkerThread

class TaskServer:
    def __init__(self, host: str, port: int, max_threads: int, task_timeout: float, data_dir: str):
        self.host = host
        self.port = port
        self.max_threads = max_threads
        self.task_timeout = task_timeout

        # This will later store a reference to the event loop (Stellar)
        self.loop = None

        # Setup data directory structure
        self.data_dir = Path(data_dir)
        self.reports_dir = self.data_dir / "reports"
        self.db_path = self.data_dir / "tasks.db"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(exist_ok=True)

        self.db = DatabaseManager(str(self.db_path))
        self.queue = CancellablePriorityQueue()

        # task_subscribers stores the task_id to listening connection mapping. subscribers_lock is the corresponding lock
        self.task_subscribers: Dict[str, asyncio.StreamWriter] = {}
        self.subscribers_lock = threading.Lock()

        # Initialize worker threads
        self.workers = []
        for _ in range(max_threads - 1):  # 1 of the threads is used by the event loop (Stellar) itself
            worker = WorkerThread(
                self.queue,
                self.db,
                self.reports_dir,
                self.task_timeout,
                self.handle_task_status
            )
            self.workers.append(worker)
            worker.start()

    def unsubscribe_writer(self, task_id: str):
        with self.subscribers_lock:
            self.task_subscribers.pop(task_id, None)

    def handle_task_status(self, task_id: str, **kwargs):
        # TODO Determine whether it'd be more performant to create the status json only after it has been confirmed there's a subscriber for the taskid
        with self.subscribers_lock:
            writer = self.task_subscribers.get(task_id)
            if writer and self.loop:
                status = kwargs.get("status")
                if status is not None:
                    asyncio.run_coroutine_threadsafe(
                        self.send_json(writer,
                                       status,
                                       upon_connection_reset=lambda: self.unsubscribe_writer(task_id)
                                       ),
                        self.loop
                    )
                elif kwargs.get("exit_code") is not None and kwargs.get("report_path") is not None:
                    # Attempt to consume the report
                    report_path = kwargs["report_path"]
                    asyncio.run_coroutine_threadsafe(
                        self.send_json(writer, {
                            "binary_data": os.path.getsize(report_path),
                            "exit_code": kwargs["exit_code"]
                        }, upon_connection_reset=lambda: self.unsubscribe_writer(task_id)), self.loop
                    )
                    asyncio.run_coroutine_threadsafe(
                        self.send_report(writer, task_id, report_path), self.loop
                    )

    async def send_json(self, writer: asyncio.StreamWriter, data, upon_connection_reset = lambda: None) -> None:
        try:
            message = json.dumps(data) + "\n"
            writer.write(message.encode())
            await writer.drain()
        except ConnectionResetError:
            print(f"Connection {writer} reset by peer")
            upon_connection_reset()
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            print("Exception in send_json", e)
            traceback.print_exc()
            writer.close()
            await writer.wait_closed()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while True:
            try:
                data = await reader.readline()
                if not data:
                    break

                request = json.loads(data.decode())

                if request == "keepalive":
                    continue

                if not isinstance(request, dict):
                    await self.send_json(writer, {"error": "Unexpected input format"})
                    continue

                if request.get("version", 0) != 0: # TODO Implement more abstract version handling to actually materialize this
                    await self.send_json(writer, {"error": "Unsupported protocol version"})
                    break

                method = request.get("method")
                if not method:
                    await self.send_json(writer, {"error": "Missing method"})
                    continue

                # TODO remove redundant reader params
                if method in ["task", "watchedtask"]:
                    await self.handle_task_request(writer, request, watch=method == "watchedtask")
                elif method == "status":
                    await self.handle_status_request(writer, request)
                elif method == "report":
                    await self.handle_report_request(writer, request)
                elif method == "cancel":
                    await self.handle_cancel_request(writer, request)
                else:
                    await self.send_json(writer, {"error": "Invalid method"})

            except json.JSONDecodeError:
                await self.send_json(writer, {"error": "Invalid JSON"})
            except Exception as e:
                print("Exception when handling request:", e) # TODO add comprehensive error logging (like a fatal field to indicate connection closure)
                traceback.print_exc()
                await self.send_json(writer, {"error": "Unexpected error, exiting."})
                break

        writer.close()
        await writer.wait_closed()

    async def handle_task_request(self, writer: asyncio.StreamWriter,
                                  request: dict, watch: bool):
        params = request.get("params")
        if not isinstance(params, dict):
            await self.send_json(writer, {"error": "Invalid or missing params"})
            return

        try:
            validate_params(params)
        except TaskValidationException as e:
            await self.send_json(writer, {"error": str(e)})
            return

        priority = request.get("priority", 0)

        # TODO remove the burden of database writes from Stellar event loop (this one is simple)
        task_id = self.db.create_task()
        self.queue.put(task_id, priority, params)

        response = {"taskid": task_id}
        await self.send_json(writer, response)

        if watch:
            with self.subscribers_lock:
                if task_id in self.task_subscribers:
                    await self.send_json(writer, {"error": "Task already being watched"})
                    return
                self.task_subscribers[task_id] = writer

    async def handle_status_request(self, writer: asyncio.StreamWriter,
                                    request: dict):
        task_id = request.get("taskid")
        if not task_id:
            await self.send_json(writer, {"error": "Missing taskid"})
            return

        running_tasks = RunningTasks()

        is_running = running_tasks.is_running(task_id)
        is_enqueued = self.queue.is_task_enqueued(task_id)
        if not (is_running or is_enqueued):
            await self.send_json(writer,
                                 {"error": "Unable to subscribe to real-time updates: "
                                           "The task has either finished or the task id is invalid"})
            return

        with self.subscribers_lock:
            if task_id in self.task_subscribers:
                await self.send_json(writer, {"error": "Task already being watched"})
                return
            await self.send_json(writer, {"result": "success", "has_execution_started": is_running})
            self.task_subscribers[task_id] = writer

    async def handle_report_request(self, writer: asyncio.StreamWriter,
                                    request: dict):
        task_id = request.get("taskid")
        if not task_id:
            await self.send_json(writer, {"error": "Missing taskid"})
            return

        start_time, end_time, report_path = self.db.get_task_status(task_id)

        if not end_time:
            await self.send_json(writer, {"error": "Task is still being processed"})
            return

        if not report_path:
            await self.send_json(writer, {"error": "Report not available or already consumed"})
            return


        try:
            content_length = os.path.getsize(report_path)
        except FileNotFoundError:
            await self.send_json(writer, {"error": "Report file not found"})
            return

        await self.send_json(writer, {"binary_data": content_length})
        await self.send_report(writer, task_id, report_path)

    async def send_report(self, writer: asyncio.StreamWriter, task_id, report_path, chunk_size=2048):
        with open(report_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                writer.write(chunk)
                await writer.drain()

        # Clear the report path from db and delete the file from filesystem
        self.db.clear_report_path(task_id)
        try:
            os.remove(report_path)
            os.rmdir(os.path.dirname(report_path))
        except FileNotFoundError:
            pass

    async def handle_cancel_request(self, writer: asyncio.StreamWriter,
                                    request: dict):
        task_id = request.get("taskid")
        if not task_id:
            await self.send_json(writer, {"error": "Missing taskid"})
            return

        start_time, end_time, _ = self.db.get_task_status(task_id)

        if start_time:
            await self.send_json(writer, {"error": "Already started"})
        elif end_time:
            await self.send_json(writer, {"error": "Already finished"})
        elif self.queue.cancel(task_id):
            await self.send_json(writer, "success")
        else:
            await self.send_json(writer, {"error": "Invalid or expired taskid"})

    async def run(self):
        server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
            reuse_address=True
        )

        self.loop = asyncio.get_running_loop()

        async with server:
            await server.serve_forever()

def main():
    parser = argparse.ArgumentParser(description='TaskExec Server')
    parser.add_argument('--host', default='0.0.0.0', help='Server host')
    parser.add_argument('--port', type=int, default=8888, help='Server port')
    parser.add_argument('--maxthreadcount', type=int, default=5, help='Maximum number of threads')
    parser.add_argument('--timeout', type=float, default=60*15, help='Task timeout in seconds')
    parser.add_argument('--datadir', default='taskexec_server_data',
                       help='Directory for all server data (database and reports)')
    parser.add_argument("--wordlist", default="/usr/share/dirb/wordlists/common.txt", help="Path to the wordlist to use for gobuster/ffuf task types.")

    args = parser.parse_args()

    globalconfig.WORDLIST_PATH = args.wordlist

    server = TaskServer(
        args.host,
        args.port,
        args.maxthreadcount,
        args.timeout,
        args.datadir
    )

    try:
        print(f"Starting server on {args.host}:{args.port}")
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\nShutting down...")
        for worker in server.workers:
            worker.stop()
        for worker in server.workers:
            worker.join()

if __name__ == "__main__":
    main()