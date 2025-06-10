"""Base hardware backend interface"""

from __future__ import annotations
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

class HardwareBackend(ABC):
    """Abstract base class for hardware backends"""
    
    def __init__(self):
        self._initialized = False
        self._lock = asyncio.Lock()
        self._state_cache: Dict[str, bool] = {}
        self._critical_points: Set[str] = set()
        self._last_read_time: float = 0
        self._read_count: int = 0
        self._write_count: int = 0
        self._error_count: int = 0
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the hardware backend"""
        pass
    
    @abstractmethod
    async def read_point(self, point_id: str) -> bool:
        """Read a single I/O point"""
        pass
    
    @abstractmethod
    async def write_point(self, point_id: str, value: bool) -> None:
        """Write to a single I/O point"""
        pass
    
    @abstractmethod
    async def read_all_points(self) -> Dict[str, bool]:
        """Read all I/O points"""
        pass
    
    @abstractmethod
    async def write_points(self, points: Dict[str, bool]) -> None:
        """Write to multiple I/O points"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the hardware backend"""
        pass
    
    def add_critical_point(self, point_id: str) -> None:
        """Add a point to the critical points set"""
        self._critical_points.add(point_id)
    
    def remove_critical_point(self, point_id: str) -> None:
        """Remove a point from the critical points set"""
        self._critical_points.discard(point_id)
    
    def is_critical_point(self, point_id: str) -> bool:
        """Check if a point is critical"""
        return point_id in self._critical_points
    
    def get_critical_points(self) -> Set[str]:
        """Get the set of critical points"""
        return self._critical_points.copy()
    
    def get_state_cache(self) -> Dict[str, bool]:
        """Get the current state cache"""
        return self._state_cache.copy()
    
    def get_last_read_time(self) -> float:
        """Get the timestamp of the last read operation"""
        return self._last_read_time
    
    def get_read_count(self) -> int:
        """Get the total number of read operations"""
        return self._read_count
    
    def get_write_count(self) -> int:
        """Get the total number of write operations"""
        return self._write_count
    
    def get_error_count(self) -> int:
        """Get the total number of errors"""
        return self._error_count
    
    def is_initialized(self) -> bool:
        """Check if the backend is initialized"""
        return self._initialized
    
    async def update_state_cache(self, states: Dict[str, bool]) -> None:
        """Update the state cache with new values"""
        async with self._lock:
            self._state_cache.update(states)
    
    async def get_cached_state(self, point_id: str) -> Optional[bool]:
        """Get the cached state for a point"""
        return self._state_cache.get(point_id)
    
    async def clear_state_cache(self) -> None:
        """Clear the state cache"""
        async with self._lock:
            self._state_cache.clear()
    
    async def reset_metrics(self) -> None:
        """Reset all performance metrics"""
        async with self._lock:
            self._read_count = 0
            self._write_count = 0
            self._error_count = 0
            self._last_read_time = 0 