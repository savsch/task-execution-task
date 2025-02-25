import re
import select
import subprocess
from typing import Dict, Optional

from task_executor import TaskExecutor
from task_executors.utils.exceptions import TaskValidationException

class NmapExecutor(TaskExecutor):
    @classmethod
    def validate(cls, request_args: Dict) -> None:
        # TODO Maybe consider using an existing nmap wrapper for more robust validation,
        #     as this might be prone to security bugs
        #     Maybe check out https://github.com/nmmapper/python3-nmap/blob/main/nmap3/nmapparser.py for this
        if not (isinstance(request_args, list) and request_args and all(
                (isinstance(item, str)) for item in request_args)):
            raise TaskValidationException(
                "args must be a list of strings")
        user_input = ''.join(request_args)
        if not re.match(r'^[a-zA-Z0-9\-\/\.:,_+=@]*$', user_input):
            raise TaskValidationException("Illegal characters in nmap args.")

    # TODO reduce code duplication here
    def execute(self, timeout: Optional[float] = None) -> int:

        # I explicitly add a --stats-every to the request_args, to make enable progress updates, when the flag isn't
        #     already requested for
        if '--stats-every' not in ''.join(self.request_args):
            self.request_args.append('--stats-every=2s')

        streams = {}
        try:
            self._process = subprocess.Popen(
                ['nmap', *self.request_args],
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
            self.output_handler.emit_error_output(str(e).encode())
            return 1
        finally:
            if self._process:
                for stream, _ in streams.values():
                    stream.close()

    # TODO reduce code duplication here
    def stop(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()  # Force kill if the process doesn't terminate