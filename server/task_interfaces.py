from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import time

class TaskType(Enum):
    ECHO = "echo"
    NMAP = "nmap"  # For future
    GOBUSTER = "gobuster"  # For future
    FFUF = "ffuf"  # For future

@dataclass
class TaskParams:
    type: TaskType
    args: List[str]

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"

@dataclass
class StatusUpdate:
    timestamp: int
    stdout: Optional[str] = None
    stderr: Optional[str] = None

class TaskOutput(ABC):
    @abstractmethod
    def emit_normal_output(self, data: str) -> None:
        pass

    @abstractmethod
    def emit_error_output(self, data: str) -> None:
        pass

    @abstractmethod
    def set_exit_code(self, code: int) -> None:
        pass