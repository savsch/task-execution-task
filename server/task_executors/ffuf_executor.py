import select
import subprocess
import traceback
from typing import Optional

import globalconfig
from task_executor import TaskExecutor
from task_executors.utils.exceptions import TaskValidationException
from task_executors.utils.miscutils import is_valid_url


class FfufExecutor(TaskExecutor):
    @classmethod
    def validate(cls, request_args: str) -> None:
        if not (isinstance(request_args, str) and is_valid_url(request_args)):
            raise TaskValidationException(
                "args must be a single string and also a valid url")

    def execute(self, timeout: Optional[float] = None) -> int:
        streams = {}
        try:
            self._process = subprocess.Popen(
                ['ffuf',  '-u', self.request_args, '-w', globalconfig.WORDLIST_PATH],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
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
            print("Exception executing ffuf task type", str(e))
            traceback.print_exc()
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