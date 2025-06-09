from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import asyncio
import logging
import time

from .types import IoPoint, IoType, PerformanceMetrics

logger = logging.getLogger(__name__)

class HardwareBackend(ABC):
    """Abstract base for hardware backends"""
    
    def __init__(self, name: str) -> None:
        self.name = name
        self.metrics = PerformanceMetrics()
        self._initialized = False
        
    @abstractmethod
    async def initialize(self, points: List[IoPoint]) -> bool:
        """Initialize hardware with I/O points"""
        pass
    
    @abstractmethod
    async def read_all(self) -> Dict[str, Any]:
        """Read all I/O points"""
        pass
    
    @abstractmethod
    async def write_point(self, point_name: str, value: Any) -> bool:
        """Write to an I/O point."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass

class SimulatedBackend(HardwareBackend):
    """Simulated hardware for testing without real hardware"""

    def __init__(self, name: str = "simulator") -> None:
        super().__init__(name)
        self._state: Dict[str, Any] = {}
        self._points: Dict[str, IoPoint] = {}
        self._read_delay = 0.001 # 1ms delay for reading
        self._write_delay = 0.001 # 1ms delay for writing

    async def initialize(self, points: List[IoPoint]) -> bool:
        """Initialize simulated hardware"""
        try:
            for point in points:
                self._points[point.name] = point

                # Set initial state
                if point.initial_state is not None:
                    self._state[point.name] = point.initial_state
                else:
                    self._state[point.name] = False
            
            self._initialized = True
            logger.info(f"Simulated backend initialzed with {len(points)} points")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize simulated backend: {e}")
            return False
    
    async def read_all(self) -> Dict[str, Any]:
        """Read all simulated I/O points"""
        start_time = time.perf_counter()

        # Simulate hardware delay
        await asyncio.sleep(self._read_delay)

        # Update metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        self.metrics.update_read_time(duration_ms)

        return self._state.copy()

    async def write_point(self, point_name: str, value: Any) -> bool:
        """Write to simulated I/O point"""
        start_time = time.perf_counter()

        try:
            if point_name not in self._points:
                logger.warning(f"Unknown point: {point_name}")
                return False
            
            point = self._points[point_name]
            if not point.io_type.value.endswith("_output"):
                logger.warning(f"Cannot write to input point: {point_name}")
                return False
            
            # Simulate hardware delay
            await asyncio.sleep(self._write_delay)

            # Update state
            self._state[point_name] = value

            # Update metrics
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.update_write_time(duration_ms)
            
            logger.debug(f"Simulated write to {point_name}: {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to write to simulated point {point_name}: {e}")
            return False
        
    async def close(self) -> None:
        """Close simulated backend"""
        self._state.clear()
        self._points.clear()
        self._initialized = False
        logger.info("Simulated backend closed")

    def simulate_input_change(self, point_name: str, value: Any) -> None:
        """Simulate input changing (for testing)"""
        if point_name in self._state:
            self._state[point_name] = value
            logger.debug(f"Simulated input change: {point_name} = {value}")

#? INFO: Placeholder for real MCP backend (we'll implement this later)
#! TODO: Implement MCPBackend
class MCPBackend(HardwareBackend):
    """MCP expander backed- placeholder for real MCP backend"""

    def __init__(self, name: str, chip_configs: List[Dict[str, Any]]) -> None:
        super().__init__(name)
        self._chip_configs = chip_configs
        #! TODO: Implement MCP Backend when hardware specs are available
    
    async def initialize(self, points: List[IoPoint]) -> bool:
        logger.info(f"MCP backend placeholder - not implementet yet")
        return False
    
    async def read_all(self) -> Dict[str, Any]:
        return {}
    
    async def write_point(self, point_name: str, value: Any) -> bool:
        return False
    
    async def close(self) -> None:
        pass

