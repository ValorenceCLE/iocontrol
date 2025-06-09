"""Tests for IoControl backends"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from iocontrol.backends import HardwareBackend, SimulatedBackend, MCPBackend
from iocontrol.types import IoPoint, IoType


class TestSimulatedBackend:
    """Test cases for SimulatedBackend"""
    
    @pytest.fixture
    def sample_points(self):
        """Sample I/O points for testing"""
        return [
            IoPoint(
                name="output_1",
                io_type=IoType.DIGITAL_OUTPUT,
                hardware_ref="sim.pin0",
                critical=False,
                description="Test output"
            ),
            IoPoint(
                name="input_1", 
                io_type=IoType.DIGITAL_INPUT,
                hardware_ref="sim.pin1",
                critical=True,
                description="Test input"
            ),
            IoPoint(
                name="analog_out",
                io_type=IoType.ANALOG_OUTPUT,
                hardware_ref="sim.pin2",
                initial_state=0.0,
                description="Test analog output"
            )
        ]
    
    async def test_initialization(self, sample_points):
        """Test backend initialization"""
        backend = SimulatedBackend("test_sim")
        
        success = await backend.initialize(sample_points)
        assert success
        assert backend._initialized
        
        # Check points were stored
        assert len(backend._points) == 3
        assert "output_1" in backend._points
        assert "input_1" in backend._points
        assert "analog_out" in backend._points
        
        # Check initial states
        assert backend._state["output_1"] is False  # Default
        assert backend._state["input_1"] is False  # Default
        assert backend._state["analog_out"] == 0.0  # From initial_state
    
    async def test_read_all(self, sample_points):
        """Test reading all I/O points"""
        backend = SimulatedBackend("test_sim")
        await backend.initialize(sample_points)
        
        # Read all points
        state = await backend.read_all()
        
        assert isinstance(state, dict)
        assert len(state) == 3
        assert "output_1" in state
        assert "input_1" in state
        assert "analog_out" in state
        
        # Check metrics updated
        assert backend.metrics.read_count > 0
        assert backend.metrics.avg_read_time_ms > 0
    
    async def test_write_point_digital(self, sample_points):
        """Test writing to digital output"""
        backend = SimulatedBackend("test_sim")
        await backend.initialize(sample_points)
        
        # Write to digital output
        success = await backend.write_point("output_1", True)
        assert success
        
        # Verify state changed
        state = await backend.read_all()
        assert state["output_1"] is True
        
        # Check metrics
        assert backend.metrics.write_count > 0
        assert backend.metrics.avg_write_time_ms > 0
    
    async def test_write_point_analog(self, sample_points):
        """Test writing to analog output"""
        backend = SimulatedBackend("test_sim")
        await backend.initialize(sample_points)
        
        # Write to analog output
        success = await backend.write_point("analog_out", 3.14)
        assert success
        
        # Verify state changed
        state = await backend.read_all()
        assert state["analog_out"] == 3.14
    
    async def test_write_to_input_fails(self, sample_points):
        """Test that writing to input points fails"""
        backend = SimulatedBackend("test_sim")
        await backend.initialize(sample_points)
        
        # Try to write to input (should fail)
        success = await backend.write_point("input_1", True)
        assert not success
        
        # Verify state unchanged
        state = await backend.read_all()
        assert state["input_1"] is False  # Still default value
    
    async def test_write_unknown_point(self, sample_points):
        """Test writing to unknown point"""
        backend = SimulatedBackend("test_sim")
        await backend.initialize(sample_points)
        
        success = await backend.write_point("unknown_point", True)
        assert not success
    
    async def test_simulate_input_change(self, sample_points):
        """Test simulating input changes"""
        backend = SimulatedBackend("test_sim")
        await backend.initialize(sample_points)
        
        # Simulate input change
        backend.simulate_input_change("input_1", True)
        
        # Verify change
        state = await backend.read_all()
        assert state["input_1"] is True
        
        # Simulate another change
        backend.simulate_input_change("input_1", False)
        state = await backend.read_all()
        assert state["input_1"] is False
    
    async def test_close(self, sample_points):
        """Test backend cleanup"""
        backend = SimulatedBackend("test_sim")
        await backend.initialize(sample_points)
        
        assert backend._initialized
        assert len(backend._state) > 0
        assert len(backend._points) > 0
        
        await backend.close()
        
        assert not backend._initialized
        assert len(backend._state) == 0
        assert len(backend._points) == 0
    
    async def test_performance_metrics(self, sample_points):
        """Test performance metrics tracking"""
        backend = SimulatedBackend("test_sim")
        await backend.initialize(sample_points)
        
        # Perform multiple operations
        for i in range(10):
            await backend.write_point("output_1", i % 2 == 0)
            await backend.read_all()
        
        # Check metrics
        assert backend.metrics.read_count == 10
        assert backend.metrics.write_count == 10
        assert backend.metrics.avg_read_time_ms > 0
        assert backend.metrics.avg_write_time_ms > 0
    
    async def test_simulated_delays(self):
        """Test that simulated delays work"""
        backend = SimulatedBackend("test_sim")
        backend._read_delay = 0.01   # 10ms delay
        backend._write_delay = 0.01  # 10ms delay
        
        points = [
            IoPoint("test", IoType.DIGITAL_OUTPUT, "sim.pin0")
        ]
        await backend.initialize(points)
        
        # Measure read time
        start_time = asyncio.get_event_loop().time()
        await backend.read_all()
        read_time = asyncio.get_event_loop().time() - start_time
        
        # Should include simulated delay
        assert read_time >= 0.009  # Allow some tolerance
        
        # Measure write time
        start_time = asyncio.get_event_loop().time()
        await backend.write_point("test", True)
        write_time = asyncio.get_event_loop().time() - start_time
        
        # Should include simulated delay
        assert write_time >= 0.009  # Allow some tolerance


class TestMCPBackend:
    """Test cases for MCPBackend (placeholder)"""
    
    async def test_mcp_backend_placeholder(self):
        """Test that MCP backend is properly stubbed"""
        backend = MCPBackend("test_mcp", [])
        
        # Should fail initialization (not implemented)
        success = await backend.initialize([])
        assert not success
        
        # Should return empty results
        state = await backend.read_all()
        assert state == {}
        
        success = await backend.write_point("test", True)
        assert not success
        
        # Should not raise errors
        await backend.close()


class TestHardwareBackendInterface:
    """Test the abstract HardwareBackend interface"""
    
    def test_abstract_methods(self):
        """Test that HardwareBackend cannot be instantiated"""
        with pytest.raises(TypeError):
            HardwareBackend("test")
    
    async def test_backend_metrics(self):
        """Test that all backends have metrics"""
        backend = SimulatedBackend("test")
        
        assert hasattr(backend, 'metrics')
        assert hasattr(backend.metrics, 'read_count')
        assert hasattr(backend.metrics, 'write_count')
        assert hasattr(backend.metrics, 'avg_read_time_ms')
        assert hasattr(backend.metrics, 'avg_write_time_ms')
        assert hasattr(backend.metrics, 'error_count')


class TestConcurrentOperations:
    """Test concurrent operations on backends"""
    
    async def test_concurrent_reads(self):
        """Test concurrent read operations"""
        backend = SimulatedBackend("test")
        
        points = [
            IoPoint(f"point_{i}", IoType.DIGITAL_INPUT, f"sim.pin{i}")
            for i in range(10)
        ]
        await backend.initialize(points)
        
        # Perform concurrent reads
        tasks = [backend.read_all() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All reads should succeed and return same data
        assert len(results) == 10
        for result in results:
            assert len(result) == 10
            assert all(f"point_{i}" in result for i in range(10))
    
    async def test_concurrent_writes(self):
        """Test concurrent write operations"""
        backend = SimulatedBackend("test")
        
        points = [
            IoPoint(f"output_{i}", IoType.DIGITAL_OUTPUT, f"sim.pin{i}")
            for i in range(10)
        ]
        await backend.initialize(points)
        
        # Perform concurrent writes
        tasks = [
            backend.write_point(f"output_{i}", i % 2 == 0)
            for i in range(10)
        ]
        results = await asyncio.gather(*tasks)
        
        # All writes should succeed
        assert all(results)
        
        # Verify final states
        state = await backend.read_all()
        for i in range(10):
            expected = i % 2 == 0
            assert state[f"output_{i}"] == expected
    
    async def test_mixed_concurrent_operations(self):
        """Test mixing reads and writes concurrently"""
        backend = SimulatedBackend("test")
        
        points = [
            IoPoint("output", IoType.DIGITAL_OUTPUT, "sim.pin0"),
            IoPoint("input", IoType.DIGITAL_INPUT, "sim.pin1")
        ]
        await backend.initialize(points)
        
        # Mix of read and write operations
        tasks = []
        for i in range(20):
            if i % 2 == 0:
                tasks.append(backend.write_point("output", i % 4 == 0))
            else:
                tasks.append(backend.read_all())
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check no exceptions occurred
        for result in results:
            assert not isinstance(result, Exception)
        
        # Verify metrics updated correctly
        assert backend.metrics.read_count == 10  # Half were reads
        assert backend.metrics.write_count == 10  # Half were writes


@pytest.mark.asyncio
async def test_backend_integration():
    """Integration test for backend usage patterns"""
    backend = SimulatedBackend("integration_test")
    
    # Setup various point types
    points = [
        IoPoint("relay_1", IoType.DIGITAL_OUTPUT, "sim.pin0", critical=False),
        IoPoint("relay_2", IoType.DIGITAL_OUTPUT, "sim.pin1", critical=True),
        IoPoint("sensor_1", IoType.DIGITAL_INPUT, "sim.pin2", critical=True),
        IoPoint("analog_sensor", IoType.ANALOG_INPUT, "sim.pin3", initial_state=2.5),
        IoPoint("pwm_output", IoType.ANALOG_OUTPUT, "sim.pin4", initial_state=0.0)
    ]
    
    success = await backend.initialize(points)
    assert success
    
    try:
        # Test various operations
        await backend.write_point("relay_1", True)
        await backend.write_point("relay_2", False)
        await backend.write_point("pwm_output", 3.3)
        
        # Simulate sensor changes
        backend.simulate_input_change("sensor_1", True)
        backend.simulate_input_change("analog_sensor", 4.2)
        
        # Read final state
        final_state = await backend.read_all()
        
        # Verify results
        assert final_state["relay_1"] is True
        assert final_state["relay_2"] is False
        assert final_state["sensor_1"] is True
        assert final_state["analog_sensor"] == 4.2
        assert final_state["pwm_output"] == 3.3
        
    finally:
        await backend.close()