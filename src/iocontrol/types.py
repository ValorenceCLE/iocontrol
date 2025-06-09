from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Union
import time

class IoType(Enum):
    """Types of I/O points"""
    DIGITAL_INPUT = "digital_input"
    DIGITAL_OUTPUT = "digital_output"
    ANALOG_INPUT = "analog_input"
    ANALOG_OUTPUT = "analog_output"



@dataclass
class IoPoint:
    """Configuration for a single I/O point."""
    name: str
    io_type: IoType
    hardware_ref: str
    critical: bool = False
    interrupt_enabled: bool = False
    pull_up: bool = False
    initial_state: Optional[Union[bool, float]] = None
    description: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class StateChange:
    """Represents a change in I/O state."""
    point_name: str
    old_value: Any
    new_value: Any
    timestamp: float
    hardware_ref: str

    @classmethod
    def create(cls, point_name: str, old_value: Any, new_value: Any, hardware_ref: str) -> StateChange:
        """Creates a new StateChange instance with current timestamp"""
        return cls(
            point_name=point_name,
            old_value=old_value,
            new_value=new_value,
            timestamp=time.time(),
            hardware_ref=hardware_ref
        )


@dataclass
class PerformanceMetrics:
    """Performance tracking."""
    read_count: int = 0
    write_count: int = 0
    avg_read_time_ms: float = 0.0
    avg_write_time_ms: float = 0.0
    error_count: int = 0

    def update_read_time(self, duration_ms: float) -> None:
        """Update average read time."""
        self.read_count += 1
        if self.avg_read_time_ms == 0:
            self.avg_read_time_ms = duration_ms
        else:
            self.avg_read_time_ms = self.avg_read_time_ms * 0.9 + duration_ms * 0.1

    def update_write_time(self, duration_ms: float) -> None:
        """Update average write time.""" 
        self.write_count += 1
        if self.avg_write_time_ms == 0:
            self.avg_write_time_ms = duration_ms
        else:
            self.avg_write_time_ms = self.avg_write_time_ms * 0.9 + duration_ms * 0.1