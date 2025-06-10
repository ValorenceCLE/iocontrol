"""MCP23017 I/O expander backend implementation"""

from __future__ import annotations
import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from .base import HardwareBackend
from .common.i2c import AsyncI2CDevice

logger = logging.getLogger(__name__)

# MCP23017 Register Addresses
IODIRA = 0x00  # I/O Direction Register A
IODIRB = 0x01  # I/O Direction Register B
IPOLA = 0x02   # Input Polarity Register A
IPOLB = 0x03   # Input Polarity Register B
GPINTENA = 0x04  # Interrupt Enable Register A
GPINTENB = 0x05  # Interrupt Enable Register B
DEFVALA = 0x06   # Default Compare Register A
DEFVALB = 0x07   # Default Compare Register B
INTCONA = 0x08   # Interrupt Control Register A
INTCONB = 0x09   # Interrupt Control Register B
IOCONA = 0x0A    # Configuration Register A
IOCONB = 0x0B    # Configuration Register B
GPPUA = 0x0C     # Pull-up Resistor Register A
GPPUB = 0x0D     # Pull-up Resistor Register B
INTFA = 0x0E     # Interrupt Flag Register A
INTFB = 0x0F     # Interrupt Flag Register B
INTCAPA = 0x10   # Interrupt Capture Register A
INTCAPB = 0x11   # Interrupt Capture Register B
GPIOA = 0x12     # Port Register A
GPIOB = 0x13     # Port Register B
OLATA = 0x14     # Output Latch Register A
OLATB = 0x15     # Output Latch Register B

@dataclass
class MCP23017Config:
    """Configuration for a single MCP23017 chip"""
    address: int
    bus_number: int = 1
    interrupt_pin: Optional[int] = None
    polarity_inversion: bool = False
    pull_ups: bool = True
    sequential_operation: bool = True

class MCP23017Chip:
    """Represents a single MCP23017 chip"""
    
    def __init__(self, config: MCP23017Config):
        self.config = config
        self.device = AsyncI2CDevice(bus_number=config.bus_number)
        self.device.set_address(config.address)
        self._port_a_state = 0
        self._port_b_state = 0
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the chip configuration"""
        if self._initialized:
            return
        
        async with self._lock:
            try:
                # Configure I/O direction (all pins as inputs initially)
                await self.device.write_byte(IODIRA, 0xFF)
                await self.device.write_byte(IODIRB, 0xFF)
                
                # Configure pull-ups if enabled
                if self.config.pull_ups:
                    await self.device.write_byte(GPPUA, 0xFF)
                    await self.device.write_byte(GPPUB, 0xFF)
                
                # Configure polarity inversion if enabled
                if self.config.polarity_inversion:
                    await self.device.write_byte(IPOLA, 0xFF)
                    await self.device.write_byte(IPOLB, 0xFF)
                
                # Configure sequential operation if enabled
                if self.config.sequential_operation:
                    await self.device.write_byte(IOCONA, 0x20)
                    await self.device.write_byte(IOCONB, 0x20)
                
                # Configure interrupt if pin specified
                if self.config.interrupt_pin is not None:
                    await self.device.write_byte(GPINTENA, 0xFF)
                    await self.device.write_byte(GPINTENB, 0xFF)
                    await self.device.write_byte(INTCONA, 0x00)
                    await self.device.write_byte(INTCONB, 0x00)
                
                self._initialized = True
                logger.info(f"Initialized MCP23017 at address 0x{self.config.address:02X}")
                
            except Exception as e:
                logger.error(f"Failed to initialize MCP23017 at address 0x{self.config.address:02X}: {e}")
                raise
    
    async def configure_pin(self, pin: int, direction: str, pull_up: bool = True) -> None:
        """Configure a single pin's direction and pull-up"""
        if not 0 <= pin <= 15:
            raise ValueError(f"Invalid pin number: {pin}")
        
        port = 'A' if pin < 8 else 'B'
        pin_mask = 1 << (pin % 8)
        
        # Get register addresses based on port
        iodir_reg = IODIRA if port == 'A' else IODIRB
        gppu_reg = GPPUA if port == 'A' else GPPUB
        
        async with self._lock:
            # Configure direction
            current_dir = await self.device.read_byte(iodir_reg)
            if direction == 'input':
                new_dir = current_dir | pin_mask
            else:  # output
                new_dir = current_dir & ~pin_mask
            await self.device.write_byte(iodir_reg, new_dir)
            
            # Configure pull-up
            if direction == 'input':
                current_pull = await self.device.read_byte(gppu_reg)
                if pull_up:
                    new_pull = current_pull | pin_mask
                else:
                    new_pull = current_pull & ~pin_mask
                await self.device.write_byte(gppu_reg, new_pull)
    
    async def read_ports(self) -> Tuple[int, int]:
        """Read both ports efficiently"""
        async with self._lock:
            if self.config.sequential_operation:
                # Read both ports in one operation
                values = await self.device.read_bytes(GPIOA, 2)
                self._port_a_state = values[0]
                self._port_b_state = values[1]
            else:
                # Read ports separately
                self._port_a_state = await self.device.read_byte(GPIOA)
                self._port_b_state = await self.device.read_byte(GPIOB)
            
            return self._port_a_state, self._port_b_state
    
    async def write_port(self, port: str, value: int) -> None:
        """Write to a port efficiently"""
        if port not in ('A', 'B'):
            raise ValueError(f"Invalid port: {port}")
        
        reg = GPIOA if port == 'A' else GPIOB
        state_attr = '_port_a_state' if port == 'A' else '_port_b_state'
        
        async with self._lock:
            await self.device.write_byte(reg, value)
            setattr(self, state_attr, value)
    
    async def read_pin(self, pin: int) -> bool:
        """Read a single pin's state"""
        if not 0 <= pin <= 15:
            raise ValueError(f"Invalid pin number: {pin}")
        
        port = 'A' if pin < 8 else 'B'
        pin_mask = 1 << (pin % 8)
        
        # Use cached state if available
        if port == 'A':
            state = self._port_a_state
        else:
            state = self._port_b_state
        
        return bool(state & pin_mask)
    
    async def write_pin(self, pin: int, value: bool) -> None:
        """Write to a single pin"""
        if not 0 <= pin <= 15:
            raise ValueError(f"Invalid pin number: {pin}")
        
        port = 'A' if pin < 8 else 'B'
        pin_mask = 1 << (pin % 8)
        
        async with self._lock:
            # Get current port state
            current = self._port_a_state if port == 'A' else self._port_b_state
            
            # Update state
            if value:
                new_state = current | pin_mask
            else:
                new_state = current & ~pin_mask
            
            # Write new state
            await self.write_port(port, new_state)
    
    async def close(self) -> None:
        """Close the chip's resources"""
        await self.device.close()

class MCPBackend(HardwareBackend):
    """MCP23017 hardware backend implementation"""
    
    def __init__(self, chip_configs: List[MCP23017Config]):
        super().__init__()
        self._chips: Dict[int, MCP23017Chip] = {}
        self._chip_configs = chip_configs
        self._critical_points: Set[str] = set()
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize all MCP23017 chips"""
        if self._initialized:
            return
        
        async with self._lock:
            try:
                # Initialize each chip
                for config in self._chip_configs:
                    chip = MCP23017Chip(config)
                    await chip.initialize()
                    self._chips[config.address] = chip
                
                self._initialized = True
                logger.info(f"Initialized {len(self._chips)} MCP23017 chips")
                
            except Exception as e:
                logger.error(f"Failed to initialize MCP23017 backend: {e}")
                raise
    
    def _get_chip_and_pin(self, point_id: str) -> Tuple[MCP23017Chip, int]:
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
    
    async def _read_chip_points(self, address: int, chip: MCP23017Chip) -> Dict[str, bool]:
        """Read all points for a single chip"""
        port_a, port_b = await chip.read_ports()
        states = {}
        
        # Process port A
        for pin in range(8):
            point_id = f"mcp{address:02x}_{pin}"
            states[point_id] = bool(port_a & (1 << pin))
        
        # Process port B
        for pin in range(8):
            point_id = f"mcp{address:02x}_{pin + 8}"
            states[point_id] = bool(port_b & (1 << pin))
        
        return states
    
    async def write_points(self, points: Dict[str, bool]) -> None:
        """Write to multiple I/O points efficiently"""
        if not self._initialized:
            raise RuntimeError("Backend not initialized")
        
        # Group writes by chip and port
        chip_writes: Dict[int, Dict[str, int]] = {}
        
        for point_id, value in points.items():
            chip, pin = self._get_chip_and_pin(point_id)
            port = 'A' if pin < 8 else 'B'
            pin_mask = 1 << (pin % 8)
            
            if chip.config.address not in chip_writes:
                chip_writes[chip.config.address] = {'A': 0, 'B': 0}
            
            if value:
                chip_writes[chip.config.address][port] |= pin_mask
            else:
                chip_writes[chip.config.address][port] &= ~pin_mask
        
        # Write to each chip
        async with self._lock:
            for address, ports in chip_writes.items():
                chip = self._chips[address]
                if 'A' in ports:
                    await chip.write_port('A', ports['A'])
                if 'B' in ports:
                    await chip.write_port('B', ports['B'])
    
    async def close(self) -> None:
        """Close all chip resources"""
        if not self._initialized:
            return
        
        async with self._lock:
            for chip in self._chips.values():
                await chip.close()
            self._chips.clear()
            self._initialized = False 