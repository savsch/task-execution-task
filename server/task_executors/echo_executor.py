import select
import subprocess
from typing import Dict, Optional

from task_executor import TaskExecutor
from task_executors.utils.exceptions import TaskValidationException

class EchoTaskExecutor(TaskExecutor):
    # params should've already been validated before __init__ is ever called

    @classmethod
    def validate(cls, request_args: Dict) -> None:
        if not (isinstance(request_args, list) and request_args and all(
                (isinstance(item, str) and item.isalnum()) for item in request_args)):
            raise TaskValidationException(
                "args must be a list of strings, each containing only alphanumeric characters")

    def execute(self, timeout: Optional[float] = None) -> int:
        streams = {}
        try:
            self._process = subprocess.Popen(
                ['echo', *self.request_args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0  # Unbuffered
            )

            # select.poll doesn't spawn new threads, so I am not disrespecting the max threadcount here
            poller = select.poll()
            poller.register(self._process.stdout, select.POLLIN)
            poller.register(self._process.stderr, select.POLLIN)

            streams = {
                self._process.stdout.fileno(): (self._process.stdout, self.output_handler.emit_normal_output),
                self._process.stderr.fileno(): (self._process.stderr, self.output_handler.emit_error_output)
            }

            while streams and self._process.poll() is None:
                for fd, event in poller.poll():
                    print("here")
                    if event & select.POLLIN:
                        stream, emit_func = streams[fd]
                        chunk = stream.read(8192)
                        if chunk:
                            emit_func(chunk)
                    elif event & (select.POLLHUP | select.POLLERR):
                        poller.unregister(fd)
                        streams.pop(fd)

            for stream, emit_func in streams.values():
                remaining = stream.read()
                if remaining:
                    emit_func(remaining)

            return self._process.wait()

        except subprocess.TimeoutExpired:
            self.stop()
            self.output_handler.emit_error_output(b"Task execution timed out")
            return 1
        except Exception as e:
            self.output_handler.emit_error_output(str(e).encode())
            return 1
        finally:
            if self._process:
                for stream, _ in streams.values():
                    stream.close()

    def stop(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()  # Force kill if the process doesn't terminate