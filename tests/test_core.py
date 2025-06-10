"""Tests for IoControl core functionality - Fixed Version"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from iocontrol import IoManager, SimulatedBackend, IoPoint, IoType


class TestIoManager:
    """Test cases for IoManager"""
    
    @pytest.fixture
    async def manager_with_backend(self):
        """Create IoManager with simulated backend"""
        manager = IoManager()
        backend = SimulatedBackend("test")
        await manager.add_backend("simulator", backend)
        return manager, backend
    
    @pytest.fixture
    def sample_config(self):
        """Sample configuration for testing"""
        return {
            "io_points": [
                {
                    "name": "test_output",
                    "io_type": "digital_output",
                    "hardware_ref": "sim.pin0",
                    "critical": False,
                    "description": "Test output"
                },
                {
                    "name": "test_input",
                    "io_type": "digital_input", 
                    "hardware_ref": "sim.pin1",
                    "critical": True,
                    "description": "Test input"
                }
            ]
        }
    
    async def test_add_backend(self, manager_with_backend):
        """Test adding backends"""
        manager, backend = manager_with_backend
        assert "simulator" in manager.backends
        assert manager.backends["simulator"] == backend
    
    async def test_configure_from_dict(self, manager_with_backend, sample_config):
        """Test configuration from dictionary"""
        manager, _ = manager_with_backend
        
        success = await manager.configure_from_dict(sample_config)
        assert success
        
        # Check points were created
        assert len(manager.points) == 2
        assert "test_output" in manager.points
        assert "test_input" in manager.points
        
        # Check critical points
        assert "test_input" in manager.critical_points
        assert "test_output" not in manager.critical_points
        
        # Check that states were initialized
        assert "test_output" in manager.current_states
        assert "test_input" in manager.current_states
    
    async def test_start_stop(self, manager_with_backend, sample_config):
        """Test starting and stopping the manager"""
        manager, _ = manager_with_backend
        
        await manager.configure_from_dict(sample_config)
        
        # Start
        await manager.start()
        assert manager._running
        assert manager._polling_task is not None
        
        # Stop
        await manager.stop()
        assert not manager._running
        assert manager._polling_task is None  # Should be cleared after stop
    
    async def test_write_read(self, manager_with_backend, sample_config):
        """Test writing and reading I/O points"""
        manager, _ = manager_with_backend
        
        await manager.configure_from_dict(sample_config)
        await manager.start()
        
        try:
            # Test write to output
            success = await manager.write("test_output", True)
            assert success
            
            # Test read
            value = await manager.read("test_output")
            assert value is True
            
            # Test write to input (should fail)
            success = await manager.write("test_input", True)
            assert not success
            
        finally:
            await manager.stop()
    
    async def test_read_all(self, manager_with_backend, sample_config):
        """Test reading all I/O points"""
        manager, _ = manager_with_backend
        
        await manager.configure_from_dict(sample_config)
        await manager.start()
        
        try:
            # Write some values
            await manager.write("test_output", True)
            
            # Read all
            all_states = await manager.read_all()
            assert isinstance(all_states, dict)
            assert "test_output" in all_states
            assert "test_input" in all_states  # Should be present after initialization
            assert all_states["test_output"] is True
            assert all_states["test_input"] is False  # Default initial value
            
        finally:
            await manager.stop()
    
    async def test_change_callbacks(self, manager_with_backend, sample_config):
        """Test change notification callbacks"""
        manager, backend = manager_with_backend
        
        await manager.configure_from_dict(sample_config)
        
        # Setup callback
        changes_received = []
        
        def change_callback(changes):
            changes_received.extend(changes)
        
        manager.on_change(change_callback)
        await manager.start()
        
        try:
            # Write to output (should trigger callback)
            await manager.write("test_output", True)
            
            # Simulate input change
            backend.simulate_input_change("test_input", True)
            
            # Wait for polling to detect change
            await asyncio.sleep(0.05)
            
            # Check callbacks were called
            assert len(changes_received) >= 1
            
        finally:
            await manager.stop()
    
    async def test_invalid_operations(self, manager_with_backend):
        """Test error handling for invalid operations"""
        manager, _ = manager_with_backend
        
        # Try to read non-existent point
        with pytest.raises(ValueError, match="Unknown I/O point"):
            await manager.read("nonexistent")
        
        # Try to write to non-existent point
        success = await manager.write("nonexistent", True)
        assert not success
    
    async def test_performance_metrics(self, manager_with_backend, sample_config):
        """Test performance metrics tracking"""
        manager, _ = manager_with_backend
        
        await manager.configure_from_dict(sample_config)
        await manager.start()
        
        try:
            # Perform operations
            await manager.write("test_output", True)
            await manager.read("test_output")
            
            # Check metrics
            assert manager.metrics.read_count > 0
            assert manager.metrics.write_count > 0
            assert manager.metrics.avg_read_time_ms >= 0
            assert manager.metrics.avg_write_time_ms >= 0
            
        finally:
            await manager.stop()


class TestAsyncBehavior:
    """Test async behavior and concurrency"""
    
    async def test_concurrent_operations(self):
        """Test concurrent read/write operations"""
        manager = IoManager()
        backend = SimulatedBackend("test")
        await manager.add_backend("simulator", backend)
        
        config = {
            "io_points": [
                {
                    "name": f"output_{i}",
                    "io_type": "digital_output",
                    "hardware_ref": f"sim.pin{i}",
                    "description": f"Test output {i}"
                }
                for i in range(10)
            ]
        }
        
        await manager.configure_from_dict(config)
        await manager.start()
        
        try:
            # Perform concurrent writes
            tasks = []
            for i in range(10):
                task = manager.write(f"output_{i}", i % 2 == 0)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            assert all(results)  # All writes should succeed
            
            # Perform concurrent reads
            tasks = []
            for i in range(10):
                task = manager.read(f"output_{i}")
                tasks.append(task)
            
            values = await asyncio.gather(*tasks)
            assert len(values) == 10
            
        finally:
            await manager.stop()
    
    async def test_polling_performance(self):
        """Test that polling doesn't block operations"""
        manager = IoManager()
        backend = SimulatedBackend("test")
        await manager.add_backend("simulator", backend)
        
        config = {
            "io_points": [
                {
                    "name": "test_output",
                    "io_type": "digital_output", 
                    "hardware_ref": "sim.pin0",
                    "description": "Test output"
                }
            ]
        }
        
        await manager.configure_from_dict(config)
        await manager.start()
        
        try:
            # Measure operation time while polling is running
            start_time = asyncio.get_event_loop().time()
            
            for _ in range(100):
                await manager.write("test_output", True)
                await manager.read("test_output")
            
            end_time = asyncio.get_event_loop().time()
            total_time_ms = (end_time - start_time) * 1000
            
            # Should complete 200 operations in reasonable time
            avg_time_per_op = total_time_ms / 200
            assert avg_time_per_op < 10  # Less than 10ms per operation
            
        finally:
            await manager.stop()


@pytest.mark.asyncio
async def test_integration_example():
    """Integration test similar to the basic example"""
    manager = IoManager()
    simulator = SimulatedBackend("test_sim")
    await manager.add_backend("simulator", simulator)
    
    config = {
        "io_points": [
            {
                "name": "relay_1",
                "io_type": "digital_output",
                "hardware_ref": "sim.pin0",
                "critical": False,
                "description": "Test relay"
            }
        ]
    }
    
    success = await manager.configure_from_dict(config)
    assert success
    
    await manager.start()
    
    try:
        # Test basic operations
        success = await manager.write("relay_1", True)
        assert success
        
        state = await manager.read("relay_1")
        assert state is True
        
        all_states = await manager.read_all()
        assert "relay_1" in all_states
        assert all_states["relay_1"] is True
        
    finally:
        await manager.stop()