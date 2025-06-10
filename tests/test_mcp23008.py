"""Tests for MCP23008 backend implementation"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List

from iocontrol.backends.mcp23008 import (
    MCP23008Backend,
    MCP23008Chip,
    MCP23008Config,
    IODIR,
    IPOL,
    GPINTEN,
    DEFVAL,
    INTCON,
    IOCON,
    GPPU,
    INTF,
    INTCAP,
    GPIO,
    OLAT
)

class TestMCP23008Chip:
    """Test cases for MCP23008Chip"""
    
    @pytest.fixture
    def chip(self):
        """Create a test chip instance"""
        config = MCP23008Config(address=0x20)
        return MCP23008Chip(config)
    
    @pytest.mark.asyncio
    async def test_initialize(self, chip):
        """Test chip initialization"""
        # Mock device methods
        chip.device.write_byte = AsyncMock()
        chip.device.read_byte = AsyncMock(return_value=0)
        
        # Initialize chip
        await chip.initialize()
        
        # Verify initialization sequence
        assert chip._initialized
        chip.device.write_byte.assert_any_call(IODIR, 0xFF)
        chip.device.write_byte.assert_any_call(GPPU, 0xFF)
    
    @pytest.mark.asyncio
    async def test_configure_pin(self, chip):
        """Test pin configuration"""
        # Mock device methods
        chip.device.write_byte = AsyncMock()
        chip.device.read_byte = AsyncMock(return_value=0)
        
        # Configure pin as input
        await chip.configure_pin(3, 'input', pull_up=True)
        chip.device.write_byte.assert_any_call(IODIR, 0x08)  # Set bit 3
        chip.device.write_byte.assert_any_call(GPPU, 0x08)   # Set bit 3
        
        # Configure pin as output
        await chip.configure_pin(3, 'output')
        chip.device.write_byte.assert_any_call(IODIR, 0x00)  # Clear bit 3
    
    @pytest.mark.asyncio
    async def test_read_write_port(self, chip):
        """Test port read/write operations"""
        # Mock device methods
        chip.device.write_byte = AsyncMock()
        chip.device.read_byte = AsyncMock(return_value=0x55)
        
        # Read port
        value = await chip.read_port()
        assert value == 0x55
        assert chip._port_state == 0x55
        
        # Write port
        await chip.write_port(0xAA)
        chip.device.write_byte.assert_called_with(GPIO, 0xAA)
        assert chip._port_state == 0xAA
    
    @pytest.mark.asyncio
    async def test_read_write_pin(self, chip):
        """Test pin read/write operations"""
        # Mock device methods
        chip.device.write_byte = AsyncMock()
        chip.device.read_byte = AsyncMock(return_value=0x55)
        
        # Read pin
        value = await chip.read_pin(3)
        assert value is True  # Bit 3 is set in 0x55
        
        # Write pin
        await chip.write_pin(3, False)
        chip.device.write_byte.assert_called_with(GPIO, 0x4D)  # Clear bit 3
    
    @pytest.mark.asyncio
    async def test_invalid_pin(self, chip):
        """Test invalid pin handling"""
        with pytest.raises(ValueError):
            await chip.configure_pin(8, 'input')  # Pin 8 is invalid
        
        with pytest.raises(ValueError):
            await chip.read_pin(8)
        
        with pytest.raises(ValueError):
            await chip.write_pin(8, True)

class TestMCP23008Backend:
    """Test cases for MCP23008Backend"""
    
    @pytest.fixture
    def backend(self):
        """Create a test backend instance"""
        configs = [
            MCP23008Config(address=0x20),
            MCP23008Config(address=0x21)
        ]
        return MCP23008Backend(configs)
    
    @pytest.mark.asyncio
    async def test_initialize(self, backend):
        """Test backend initialization"""
        # Mock chip initialization
        with patch('iocontrol.backends.mcp23008.MCP23008Chip') as mock_chip:
            mock_chip.return_value.initialize = AsyncMock()
            mock_chip.return_value.device = MagicMock()
            
            await backend.initialize()
            
            assert backend._initialized
            assert len(backend._chips) == 2
            assert 0x20 in backend._chips
            assert 0x21 in backend._chips
    
    @pytest.mark.asyncio
    async def test_read_write_point(self, backend):
        """Test point read/write operations"""
        # Mock chip operations
        mock_chip = MagicMock()
        mock_chip.read_pin = AsyncMock(return_value=True)
        mock_chip.write_pin = AsyncMock()
        backend._chips = {0x20: mock_chip}
        backend._initialized = True
        
        # Read point
        value = await backend.read_point("mcp20_3")
        assert value is True
        mock_chip.read_pin.assert_called_with(3)
        
        # Write point
        await backend.write_point("mcp20_3", False)
        mock_chip.write_pin.assert_called_with(3, False)
    
    @pytest.mark.asyncio
    async def test_read_all_points(self, backend):
        """Test reading all points"""
        # Mock chip operations
        mock_chip = MagicMock()
        mock_chip.read_port = AsyncMock(return_value=0x55)
        backend._chips = {0x20: mock_chip}
        backend._initialized = True
        
        # Read all points
        states = await backend.read_all_points()
        
        # Verify results
        assert len(states) == 8
        assert states["mcp20_0"] is True
        assert states["mcp20_1"] is False
        assert states["mcp20_2"] is True
        assert states["mcp20_3"] is False
    
    @pytest.mark.asyncio
    async def test_write_points(self, backend):
        """Test writing multiple points"""
        # Mock chip operations
        mock_chip = MagicMock()
        mock_chip.write_port = AsyncMock()
        backend._chips = {0x20: mock_chip}
        backend._initialized = True
        
        # Write multiple points
        points = {
            "mcp20_0": True,
            "mcp20_1": False,
            "mcp20_2": True
        }
        await backend.write_points(points)
        
        # Verify write operation
        mock_chip.write_port.assert_called_with(0x05)  # Bits 0 and 2 set
    
    @pytest.mark.asyncio
    async def test_invalid_point_id(self, backend):
        """Test invalid point ID handling"""
        backend._initialized = True
        
        with pytest.raises(ValueError):
            await backend.read_point("invalid_format")
        
        with pytest.raises(ValueError):
            await backend.write_point("invalid_format", True)
    
    @pytest.mark.asyncio
    async def test_uninitialized_operations(self, backend):
        """Test operations before initialization"""
        with pytest.raises(RuntimeError):
            await backend.read_point("mcp20_0")
        
        with pytest.raises(RuntimeError):
            await backend.write_point("mcp20_0", True)
        
        with pytest.raises(RuntimeError):
            await backend.read_all_points()
        
        with pytest.raises(RuntimeError):
            await backend.write_points({"mcp20_0": True})

@pytest.mark.asyncio
async def test_integration_example():
    """Integration test example"""
    # Create backend with two chips
    configs = [
        MCP23008Config(address=0x20),
        MCP23008Config(address=0x21)
    ]
    backend = MCP23008Backend(configs)
    
    # Mock chip operations
    with patch('iocontrol.backends.mcp23008.MCP23008Chip') as mock_chip:
        mock_chip.return_value.initialize = AsyncMock()
        mock_chip.return_value.read_port = AsyncMock(return_value=0x55)
        mock_chip.return_value.write_port = AsyncMock()
        mock_chip.return_value.device = MagicMock()
        
        # Initialize backend
        await backend.initialize()
        
        # Configure some points
        points = {
            "mcp20_0": True,  # Output on first chip
            "mcp20_1": False,
            "mcp21_0": True,  # Output on second chip
            "mcp21_1": False
        }
        
        # Write points
        await backend.write_points(points)
        
        # Read all points
        states = await backend.read_all_points()
        
        # Verify results
        assert len(states) == 16  # 8 pins per chip
        assert states["mcp20_0"] is True
        assert states["mcp20_1"] is False
        assert states["mcp21_0"] is True
        assert states["mcp21_1"] is False
        
        # Close backend
        await backend.close() 