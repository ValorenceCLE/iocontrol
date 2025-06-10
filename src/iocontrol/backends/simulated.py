"""Simulated hardware backend for testing"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Dict, Optional
from .base import HardwareBackend

logger = logging.getLogger(__name__)

class SimulatedBackend(HardwareBackend):
    """Simulated hardware backend for testing"""
    
    def __init__(self, initial_states: Optional[Dict[str, bool]] = None):
        super().__init__()
        self._states = initial_states or {}
        self._simulated_delay = 0.001  # 1ms delay to simulate hardware
        self._error_rate = 0.0  # Probability of simulated errors
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize the simulated backend"""
        if self._initialized:
            return
        
        async with self._lock:
            # Simulate initialization delay
            await asyncio.sleep(self._simulated_delay)
            self._initialized = True
            logger.info("Initialized simulated backend")
    
    async def read_point(self, point_id: str) -> bool:
        """Read a single I/O point"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        async with self._lock:
            # Simulate read delay
            await asyncio.sleep(self._simulated_delay)
            
            # Simulate random errors
            if self._error_rate > 0 and time.random() < self._error_rate:
                self._error_count += 1
                raise RuntimeError("Simulated read error")
            
            self._read_count += 1
            self._last_read_time = time.perf_counter()
            
            # Return current state or default to False
            return self._states.get(point_id, False)
    
    async def write_point(self, point_id: str, value: bool) -> None:
        """Write to a single I/O point"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        async with self._lock:
            # Simulate write delay
            await asyncio.sleep(self._simulated_delay)
            
            # Simulate random errors
            if self._error_rate > 0 and time.random() < self._error_rate:
                self._error_count += 1
                raise RuntimeError("Simulated write error")
            
            self._write_count += 1
            self._states[point_id] = value
    
    async def read_all_points(self) -> Dict[str, bool]:
        """Read all I/O points"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        async with self._lock:
            # Simulate read delay
            await asyncio.sleep(self._simulated_delay)
            
            # Simulate random errors
            if self._error_rate > 0 and time.random() < self._error_rate:
                self._error_count += 1
                raise RuntimeError("Simulated read error")
            
            self._read_count += 1
            self._last_read_time = time.perf_counter()
            
            return self._states.copy()
    
    async def write_points(self, points: Dict[str, bool]) -> None:
        """Write to multiple I/O points"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        async with self._lock:
            # Simulate write delay
            await asyncio.sleep(self._simulated_delay)
            
            # Simulate random errors
            if self._error_rate > 0 and time.random() < self._error_rate:
                self._error_count += 1
                raise RuntimeError("Simulated write error")
            
            self._write_count += 1
            self._states.update(points)
    
    async def close(self) -> None:
        """Close the simulated backend"""
        if not self._initialized:
            return
        
        async with self._lock:
            self._states.clear()
            self._initialized = False
            logger.info("Closed simulated backend")
    
    def set_simulated_delay(self, delay: float) -> None:
        """Set the simulated delay for operations"""
        self._simulated_delay = max(0.0, delay)
    
    def set_error_rate(self, rate: float) -> None:
        """Set the probability of simulated errors"""
        self._error_rate = max(0.0, min(1.0, rate))
    
    def get_simulated_states(self) -> Dict[str, bool]:
        """Get the current simulated states"""
        return self._states.copy()
    
    def set_simulated_states(self, states: Dict[str, bool]) -> None:
        """Set the simulated states"""
        self._states = states.copy() 