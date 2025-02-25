from abc import ABC, abstractmethod

class TaskOutput(ABC):
    @abstractmethod
    def emit_normal_output(self, data: bytes) -> None:
        pass

    @abstractmethod
    def emit_error_output(self, data: bytes) -> None:
        pass

    # TODO separate the task execution results into three separate files, not just one: stdout, stderr and exit_code
    # @abstractmethod
    # def set_exit_code(self, code: int) -> None:
    #     pass
