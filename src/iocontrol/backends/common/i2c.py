"""Common I2C device functionality"""

from __future__ import annotations
import asyncio
import logging
import smbus2
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class AsyncI2CDevice:
    """Asynchronous I2C device with thread pool for hardware operations"""
    
    def __init__(self, bus_number: int = 1):
        self._bus = smbus2.SMBus(bus_number)
        self._address = None
        self._executor = ThreadPoolExecutor(max_workers=1)  # Single worker for I2C
        self._lock = asyncio.Lock()  # Lock for thread safety
        self._batch_lock = asyncio.Lock()  # Lock for batch operations
        self._pending_writes: List[tuple] = []  # List of (register, value) tuples
        self._batch_size = 16  # Maximum number of writes to batch
        self._batch_timeout = 0.001  # Maximum time to wait for batch
    
    def set_address(self, address: int) -> None:
        """Set the I2C device address"""
        self._address = address
    
    async def write_byte(self, register: int, value: int) -> None:
        """Write a byte to a register asynchronously"""
        if self._address is None:
            raise ValueError("I2C address not set")
        
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(
                self._executor,
                self._bus.write_byte_data,
                self._address,
                register,
                value
            )
    
    async def read_byte(self, register: int) -> int:
        """Read a byte from a register asynchronously"""
        if self._address is None:
            raise ValueError("I2C address not set")
        
        async with self._lock:
            return await asyncio.get_event_loop().run_in_executor(
                self._executor,
                self._bus.read_byte_data,
                self._address,
                register
            )
    
    async def write_bytes(self, register: int, values: List[int]) -> None:
        """Write multiple bytes to sequential registers asynchronously"""
        if self._address is None:
            raise ValueError("I2C address not set")
        
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(
                self._executor,
                self._bus.write_i2c_block_data,
                self._address,
                register,
                values
            )
    
    async def read_bytes(self, register: int, length: int) -> List[int]:
        """Read multiple bytes from sequential registers asynchronously"""
        if self._address is None:
            raise ValueError("I2C address not set")
        
        async with self._lock:
            return await asyncio.get_event_loop().run_in_executor(
                self._executor,
                self._bus.read_i2c_block_data,
                self._address,
                register,
                length
            )
    
    async def batch_write_byte(self, register: int, value: int) -> None:
        """Add a write operation to the batch"""
        async with self._batch_lock:
            self._pending_writes.append((register, value))
            
            # Process batch if it's full
            if len(self._pending_writes) >= self._batch_size:
                await self._process_batch()
    
    async def _process_batch(self) -> None:
        """Process pending write operations"""
        if not self._pending_writes:
            return
        
        async with self._batch_lock:
            # Group writes by register
            register_writes: Dict[int, List[int]] = {}
            for register, value in self._pending_writes:
                if register not in register_writes:
                    register_writes[register] = []
                register_writes[register].append(value)
            
            # Clear pending writes
            self._pending_writes.clear()
        
        # Process each register's writes
        async with self._lock:
            for register, values in register_writes.items():
                await self.write_bytes(register, values)
    
    async def flush_batch(self) -> None:
        """Flush any pending write operations"""
        await self._process_batch()
    
    async def close(self) -> None:
        """Close the I2C bus and executor"""
        try:
            # Flush any pending writes
            await self.flush_batch()
            
            # Shutdown executor
            self._executor.shutdown(wait=True)
            
            # Close I2C bus
            self._bus.close()
            
        except Exception as e:
            logger.error(f"Error closing I2C device: {e}")
            raise 