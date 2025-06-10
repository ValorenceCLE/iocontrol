"""MCP23008 I/O expander backend implementation"""

from __future__ import annotations
import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from .base import HardwareBackend
from .common.i2c import AsyncI2CDevice

logger = logging.getLogger(__name__)

# MCP23008 Register Addresses
IODIR = 0x00    # I/O Direction Register
IPOL = 0x01     # Input Polarity Register
GPINTEN = 0x02  # Interrupt Enable Register
DEFVAL = 0x03   # Default Compare Register
INTCON = 0x04   # Interrupt Control Register
IOCON = 0x05    # Configuration Register
GPPU = 0x06     # Pull-up Resistor Register
INTF = 0x07     # Interrupt Flag Register
INTCAP = 0x08   # Interrupt Capture Register
GPIO = 0x09     # Port Register
OLAT = 0x0A     # Output Latch Register

@dataclass
class MCP23008Config:
    """Configuration for a single MCP23008 chip"""
    address: int
    bus_number: int = 1
    interrupt_pin: Optional[int] = None
    polarity_inversion: bool = False
    pull_ups: bool = True
    sequential_operation: bool = True

class MCP23008Chip:
    """Represents a single MCP23008 chip"""
    
    def __init__(self, config: MCP23008Config):
        self.config = config
        self.device = AsyncI2CDevice(bus_number=config.bus_number)
        self.device.set_address(config.address)
        self._port_state = 0
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the chip configuration"""
        if self._initialized:
            return
        
        async with self._lock:
            try:
                # Configure I/O direction (all pins as inputs initially)
                await self.device.write_byte(IODIR, 0xFF)
                
                # Configure pull-ups if enabled
                if self.config.pull_ups:
                    await self.device.write_byte(GPPU, 0xFF)
                
                # Configure polarity inversion if enabled
                if self.config.polarity_inversion:
                    await self.device.write_byte(IPOL, 0xFF)
                
                # Configure sequential operation if enabled
                if self.config.sequential_operation:
                    await self.device.write_byte(IOCON, 0x20)
                
                # Configure interrupt if pin specified
                if self.config.interrupt_pin is not None:
                    await self.device.write_byte(GPINTEN, 0xFF)
                    await self.device.write_byte(INTCON, 0x00)
                
                self._initialized = True
                logger.info(f"Initialized MCP23008 at address 0x{self.config.address:02X}")
                
            except Exception as e:
                logger.error(f"Failed to initialize MCP23008 at address 0x{self.config.address:02X}: {e}")
                raise
    
    async def configure_pin(self, pin: int, direction: str, pull_up: bool = True) -> None:
        """Configure a single pin's direction and pull-up"""
        if not 0 <= pin <= 7:
            raise ValueError(f"Invalid pin number: {pin}")
        
        pin_mask = 1 << pin
        
        async with self._lock:
            # Configure direction
            current_dir = await self.device.read_byte(IODIR)
            if direction == 'input':
                new_dir = current_dir | pin_mask
            else:  # output
                new_dir = current_dir & ~pin_mask
            await self.device.write_byte(IODIR, new_dir)
            
            # Configure pull-up
            if direction == 'input':
                current_pull = await self.device.read_byte(GPPU)
                if pull_up:
                    new_pull = current_pull | pin_mask
                else:
                    new_pull = current_pull & ~pin_mask
                await self.device.write_byte(GPPU, new_pull)
    
    async def read_port(self) -> int:
        """Read the port state efficiently"""
        async with self._lock:
            self._port_state = await self.device.read_byte(GPIO)
            return self._port_state
    
    async def write_port(self, value: int) -> None:
        """Write to the port efficiently"""
        async with self._lock:
            await self.device.write_byte(GPIO, value)
            self._port_state = value
    
    async def read_pin(self, pin: int) -> bool:
        """Read a single pin's state"""
        if not 0 <= pin <= 7:
            raise ValueError(f"Invalid pin number: {pin}")
        
        pin_mask = 1 << pin
        
        # Use cached state if available
        state = self._port_state
        
        return bool(state & pin_mask)
    
    async def write_pin(self, pin: int, value: bool) -> None:
        """Write to a single pin"""
        if not 0 <= pin <= 7:
            raise ValueError(f"Invalid pin number: {pin}")
        
        pin_mask = 1 << pin
        
        async with self._lock:
            # Get current port state
            current = self._port_state
            
            # Update state
            if value:
                new_state = current | pin_mask
            else:
                new_state = current & ~pin_mask
            
            # Write new state
            await self.write_port(new_state)
    
    async def close(self) -> None:
        """Close the chip's resources"""
        await self.device.close()

class MCP23008Backend(HardwareBackend):
    """MCP23008 hardware backend implementation"""
    
    def __init__(self, chip_configs: List[MCP23008Config]):
        super().__init__()
        self._chips: Dict[int, MCP23008Chip] = {}
        self._chip_configs = chip_configs
        self._critical_points: Set[str] = set()
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize all MCP23008 chips"""
        if self._initialized:
            return
        
        async with self._lock:
            try:
                # Initialize each chip
                for config in self._chip_configs:
                    chip = MCP23008Chip(config)
                    await chip.initialize()
                    self._chips[config.address] = chip
                
                self._initialized = True
                logger.info(f"Initialized {len(self._chips)} MCP23008 chips")
                
            except Exception as e:
                logger.error(f"Failed to initialize MCP23008 backend: {e}")
                raise
    
    def _get_chip_and_pin(self, point_id: str) -> Tuple[MCP23008Chip, int]:
        """Get the chip and pin number for a point ID"""
        try:
            # Parse point ID format: "mcp<address>_<pin>"
            _, addr_str, pin_str = point_id.split('_')
            address = int(addr_str, 16)  # Convert hex address to int
            pin = int(pin_str)
            
            if address not in self._chips:
                raise ValueError(f"No chip found at address 0x{address:02X}")
            
            return self._chips[address], pin
            
        except ValueError as e:
            raise ValueError(f"Invalid point ID format: {point_id}") from e
    
    async def read_point(self, point_id: str) -> bool:
        """Read a single I/O point"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        chip, pin = self._get_chip_and_pin(point_id)
        return await chip.read_pin(pin)
    
    async def write_point(self, point_id: str, value: bool) -> None:
        """Write to a single I/O point"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        chip, pin = self._get_chip_and_pin(point_id)
        await chip.write_pin(pin, value)
    
    async def read_all_points(self) -> Dict[str, bool]:
        """Read all I/O points efficiently"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        states = {}
        
        # Read all chips in parallel
        async with self._lock:
            read_tasks = []
            for address, chip in self._chips.items():
                read_tasks.append(self._read_chip_points(address, chip))
            
            # Wait for all reads to complete
            chip_states = await asyncio.gather(*read_tasks)
            
            # Combine results
            for chip_states_dict in chip_states:
                states.update(chip_states_dict)
        
        return states
    
    async def _read_chip_points(self, address: int, chip: MCP23008Chip) -> Dict[str, bool]:
        """Read all points for a single chip"""
        port_state = await chip.read_port()
        states = {}
        
        # Process all pins
        for pin in range(8):
            point_id = f"mcp{address:02x}_{pin}"
            states[point_id] = bool(port_state & (1 << pin))
        
        return states
    
    async def write_points(self, points: Dict[str, bool]) -> None:
        """Write to multiple I/O points efficiently"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        # Group writes by chip
        chip_writes: Dict[int, int] = {}
        
        for point_id, value in points.items():
            chip, pin = self._get_chip_and_pin(point_id)
            pin_mask = 1 << pin
            
            if chip.config.address not in chip_writes:
                chip_writes[chip.config.address] = 0
            
            if value:
                chip_writes[chip.config.address] |= pin_mask
            else:
                chip_writes[chip.config.address] &= ~pin_mask
        
        # Write to each chip
        async with self._lock:
            for address, value in chip_writes.items():
                chip = self._chips[address]
                await chip.write_port(value)
    
    async def close(self) -> None:
        """Close all chip resources"""
        if not self._initialized:
            return
        
        async with self._lock:
            for chip in self._chips.values():
                await chip.close()
            self._chips.clear()
            self._initialized = False 