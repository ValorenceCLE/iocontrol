from .core import IoManager
from .types import IoPoint, IoType, StateChange, PerformanceMetrics
from .backends import HardwareBackend, SimulatedBackend, MCPBackend

__version__ = "0.1.0"
__author__ = "Landon Bell"
__email__ = "landon.bell@valorence.com"
__license__ = "MIT"
__url__ = "https://github.com/ValorenceCLE/iocontrol"
__description__ = "High-performance asynchronous I/O control for embedded systems"
__keywords__ = ["I/O", "hardware", "embedded", "asyncio"]
__classifiers__ = [
    "Development Status :: 4 - Beta",
]

__all__ = [
    "IoManager",
    "IoPoint",
    "IoType",
    "StateChange",
    "PerformanceMetrics",
    "HardwareBackend",
    "SimulatedBackend",
    "MCPBackend"
]