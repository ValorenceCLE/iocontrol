"""Tests for IoControl hardware backends"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import time

from iocontrol.backends import (
    HardwareBackend,
    MCPBackend,
    MCP23017Config,
    MCP23017Chip,
    SimulatedBackend
)
from iocontrol.types import IoPoint, IoType

class TestSimulatedBackend:
    """Test cases for SimulatedBackend"""
    
    @pytest.fixture
    def sample_points(self):
        """Sample I/O points for testing"""
        return [
            IoPoint(
                name="digital_in",
                io_type=IoType.DIGITAL_INPUT,
                hardware_ref="sim_0",
                description="Digital input"
            ),
            IoPoint(
                name="digital_out",
                io_type=IoType.DIGITAL_OUTPUT,
                hardware_ref="sim_1",
                description="Digital output",
                initial_state=False
            ),
            IoPoint(
                name="analog_in",
                io_type=IoType.ANALOG_INPUT,
                hardware_ref="sim_2",
                description="Analog input"
            ),
            IoPoint(
                name="analog_out",
                io_type=IoType.ANALOG_OUTPUT,
                hardware_ref="sim_3",
                description="Analog output",
                initial_state=0.0
            )
        ]
    
    @pytest.mark.asyncio
    async def test_initialization(self, sample_points):
        """Test backend initialization"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        assert backend.is_initialized()
        assert backend.get_read_count() == 0
        assert backend.get_write_count() == 0
        assert backend.get_error_count() == 0
    
    @pytest.mark.asyncio
    async def test_read_all(self, sample_points):
        """Test reading all points"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Set some initial states
        states = {
            "digital_in": True,
            "digital_out": False,
            "analog_in": 3.14,
            "analog_out": 0.0
        }
        backend.set_simulated_states(states)
        
        # Read all points
        result = await backend.read_all_points()
        
        assert result == states
        assert backend.get_read_count() == 1
        assert backend.get_error_count() == 0
    
    @pytest.mark.asyncio
    async def test_write_point_digital(self, sample_points):
        """Test writing to digital points"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Write to digital output
        await backend.write_point("digital_out", True)
        
        # Verify state
        states = backend.get_simulated_states()
        assert states["digital_out"] is True
        assert backend.get_write_count() == 1
    
    @pytest.mark.asyncio
    async def test_write_point_analog(self, sample_points):
        """Test writing to analog points"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Write to analog output
        await backend.write_point("analog_out", 3.14)
        
        # Verify state
        states = backend.get_simulated_states()
        assert states["analog_out"] == 3.14
        assert backend.get_write_count() == 1
    
    @pytest.mark.asyncio
    async def test_write_to_input_fails(self, sample_points):
        """Test writing to input points fails"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Try to write to input
        with pytest.raises(ValueError):
            await backend.write_point("digital_in", True)
        
        assert backend.get_error_count() == 1
    
    @pytest.mark.asyncio
    async def test_write_unknown_point(self, sample_points):
        """Test writing to unknown point fails"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        with pytest.raises(ValueError):
            await backend.write_point("unknown_point", True)
        
        assert backend.get_error_count() == 1
    
    @pytest.mark.asyncio
    async def test_simulate_input_change(self, sample_points):
        """Test simulating input changes"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Simulate input change
        backend.set_simulated_states({"digital_in": True})
        
        # Read the point
        value = await backend.read_point("digital_in")
        assert value is True
    
    @pytest.mark.asyncio
    async def test_close(self, sample_points):
        """Test closing the backend"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        await backend.close()
        assert not backend.is_initialized()
    
    @pytest.mark.asyncio
    async def test_performance_metrics(self, sample_points):
        """Test performance metrics tracking"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Perform some operations
        await backend.read_point("digital_in")
        await backend.write_point("digital_out", True)
        
        assert backend.get_read_count() == 1
        assert backend.get_write_count() == 1
        assert backend.get_error_count() == 0
    
    @pytest.mark.asyncio
    async def test_simulated_delays(self):
        """Test simulated operation delays"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Set delays
        backend.set_simulated_delay(0.1)  # 100ms delay
        
        # Measure operation time
        start_time = time.time()
        await backend.read_point("digital_in")
        duration = time.time() - start_time
        
        assert duration >= 0.1  # Should take at least 100ms
    
    @pytest.mark.asyncio
    async def test_error_rate(self):
        """Test simulated error rate"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Set 100% error rate
        backend.set_error_rate(1.0)
        
        # Operations should fail
        with pytest.raises(RuntimeError):
            await backend.read_point("digital_in")
        
        assert backend.get_error_count() == 1

class TestMCPBackend:
    """Test cases for MCP23017 backend"""
    
    @pytest.fixture
    def mock_i2c_device(self):
        """Create a mock I2C device"""
        device = AsyncMock()
        device.read_byte.return_value = 0
        device.read_bytes.return_value = [0, 0]
        return device
    
    @pytest.fixture
    def chip_config(self):
        """Create a chip configuration"""
        return MCP23017Config(
            address=0x20,
            bus_number=1,
            pull_ups=True,
            sequential_operation=True
        )
    
    @pytest.mark.asyncio
    async def test_chip_initialization(self, chip_config, mock_i2c_device):
        """Test MCP23017 chip initialization"""
        chip = MCP23017Chip(chip_config)
        chip.device = mock_i2c_device
        
        await chip.initialize()
        
        # Verify initialization sequence
        mock_i2c_device.write_byte.assert_any_call(0x00, 0xFF)  # IODIRA
        mock_i2c_device.write_byte.assert_any_call(0x01, 0xFF)  # IODIRB
        mock_i2c_device.write_byte.assert_any_call(0x0C, 0xFF)  # GPPUA
        mock_i2c_device.write_byte.assert_any_call(0x0D, 0xFF)  # GPPUB
        mock_i2c_device.write_byte.assert_any_call(0x0A, 0x20)  # IOCONA
        mock_i2c_device.write_byte.assert_any_call(0x0B, 0x20)  # IOCONB
    
    @pytest.mark.asyncio
    async def test_chip_pin_configuration(self, chip_config, mock_i2c_device):
        """Test pin configuration"""
        chip = MCP23017Chip(chip_config)
        chip.device = mock_i2c_device
        await chip.initialize()
        
        # Configure pin as output
        await chip.configure_pin(0, 'output', pull_up=False)
        mock_i2c_device.write_byte.assert_any_call(0x00, 0xFE)  # IODIRA
        
        # Configure pin as input with pull-up
        await chip.configure_pin(8, 'input', pull_up=True)
        mock_i2c_device.write_byte.assert_any_call(0x01, 0xFF)  # IODIRB
        mock_i2c_device.write_byte.assert_any_call(0x0D, 0xFF)  # GPPUB
    
    @pytest.mark.asyncio
    async def test_chip_read_write(self, chip_config, mock_i2c_device):
        """Test reading and writing pins"""
        chip = MCP23017Chip(chip_config)
        chip.device = mock_i2c_device
        await chip.initialize()
        
        # Configure pin as output
        await chip.configure_pin(0, 'output')
        
        # Write to pin
        await chip.write_pin(0, True)
        mock_i2c_device.write_byte.assert_any_call(0x12, 0x01)  # GPIOA
        
        # Read pin
        mock_i2c_device.read_byte.return_value = 0x01
        value = await chip.read_pin(0)
        assert value is True
    
    @pytest.mark.asyncio
    async def test_backend_initialization(self, chip_config):
        """Test MCPBackend initialization"""
        backend = MCPBackend([chip_config])
        await backend.initialize()
        
        assert backend.is_initialized()
        assert len(backend._chips) == 1
    
    @pytest.mark.asyncio
    async def test_backend_read_write(self, chip_config, mock_i2c_device):
        """Test backend read/write operations"""
        backend = MCPBackend([chip_config])
        chip = MCP23017Chip(chip_config)
        chip.device = mock_i2c_device
        backend._chips[chip_config.address] = chip
        await backend.initialize()
        
        # Write to point
        await backend.write_point("mcp20_0", True)
        mock_i2c_device.write_byte.assert_any_call(0x12, 0x01)  # GPIOA
        
        # Read point
        mock_i2c_device.read_byte.return_value = 0x01
        value = await backend.read_point("mcp20_0")
        assert value is True
    
    @pytest.mark.asyncio
    async def test_backend_batch_operations(self, chip_config, mock_i2c_device):
        """Test batch read/write operations"""
        backend = MCPBackend([chip_config])
        chip = MCP23017Chip(chip_config)
        chip.device = mock_i2c_device
        backend._chips[chip_config.address] = chip
        await backend.initialize()
        
        # Batch write
        await backend.write_points({
            "mcp20_0": True,
            "mcp20_1": True
        })
        mock_i2c_device.write_byte.assert_any_call(0x12, 0x03)  # GPIOA
        
        # Batch read
        mock_i2c_device.read_bytes.return_value = [0x03, 0x00]
        states = await backend.read_all_points()
        assert states["mcp20_0"] is True
        assert states["mcp20_1"] is True

class TestHardwareBackendInterface:
    """Test cases for HardwareBackend interface"""
    
    def test_abstract_methods(self):
        """Test that HardwareBackend is abstract"""
        with pytest.raises(TypeError):
            HardwareBackend()
    
    @pytest.mark.asyncio
    async def test_backend_metrics(self):
        """Test backend metrics functionality"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Add critical point
        backend.add_critical_point("test_point")
        assert backend.is_critical_point("test_point")
        
        # Remove critical point
        backend.remove_critical_point("test_point")
        assert not backend.is_critical_point("test_point")
        
        # Test state cache
        await backend.update_state_cache({"test_point": True})
        cached_state = await backend.get_cached_state("test_point")
        assert cached_state is True
        
        # Clear cache
        await backend.clear_state_cache()
        cached_state = await backend.get_cached_state("test_point")
        assert cached_state is None

class TestConcurrentOperations:
    """Test concurrent operations on backends"""
    
    @pytest.mark.asyncio
    async def test_concurrent_reads(self):
        """Test concurrent read operations"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Set initial state
        backend.set_simulated_states({"test_point": True})
        
        # Perform concurrent reads
        async def read_point():
            return await backend.read_point("test_point")
        
        results = await asyncio.gather(*[read_point() for _ in range(10)])
        assert all(result is True for result in results)
    
    @pytest.mark.asyncio
    async def test_concurrent_writes(self):
        """Test concurrent write operations"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Perform concurrent writes
        async def write_point(value):
            await backend.write_point("test_point", value)
        
        await asyncio.gather(*[write_point(True) for _ in range(10)])
        
        # Verify final state
        value = await backend.read_point("test_point")
        assert value is True
    
    @pytest.mark.asyncio
    async def test_mixed_concurrent_operations(self):
        """Test mixed concurrent read/write operations"""
        backend = SimulatedBackend()
        await backend.initialize()
        
        # Set initial state
        backend.set_simulated_states({"test_point": False})
        
        # Perform mixed operations
        async def read_point():
            return await backend.read_point("test_point")
        
        async def write_point(value):
            await backend.write_point("test_point", value)
        
        # Start with reads
        read_tasks = [read_point() for _ in range(5)]
        # Add writes
        write_tasks = [write_point(True) for _ in range(5)]
        
        # Run all operations concurrently
        results = await asyncio.gather(*(read_tasks + write_tasks))
        
        # Verify final state
        final_value = await backend.read_point("test_point")
        assert final_value is True

@pytest.mark.asyncio
async def test_backend_integration():
    """Test integration between different backend types"""
    # Create backends
    sim_backend = SimulatedBackend()
    mcp_backend = MCPBackend([MCP23017Config(address=0x20)])
    
    # Initialize backends
    await sim_backend.initialize()
    await mcp_backend.initialize()
    
    # Test operations on both backends
    await sim_backend.write_point("sim_0", True)
    await mcp_backend.write_point("mcp20_0", True)
    
    # Read from both backends
    sim_value = await sim_backend.read_point("sim_0")
    mcp_value = await mcp_backend.read_point("mcp20_0")
    
    assert sim_value is True
    assert mcp_value is True
    
    # Clean up
    await sim_backend.close()
    await mcp_backend.close()