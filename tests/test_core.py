"""Tests for IoControl core functionality"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, List

from iocontrol.core.manager import IoManager, PollingConfig
from iocontrol.core.metrics import PerformanceMonitor
from iocontrol.types import IoPoint, IoType, StateChange
from iocontrol.backends import SimulatedBackend

class TestIoManager:
    """Test cases for IoManager"""
    
    @pytest.fixture
    async def manager_with_backend(self):
        """Create IoManager with simulated backend"""
        manager = IoManager()
        backend = SimulatedBackend()
        await manager.add_backend("simulator", backend)
        return manager
    
    @pytest.fixture
    def sample_config(self):
        """Sample configuration for testing"""
        return {
            "io_points": [
                {
                    "name": "digital_in",
                    "io_type": "digital_input",
                    "hardware_ref": "sim_0",
                    "critical": True,
                    "description": "Digital input"
                },
                {
                    "name": "digital_out",
                    "io_type": "digital_output",
                    "hardware_ref": "sim_1",
                    "description": "Digital output"
                },
                {
                    "name": "analog_in",
                    "io_type": "analog_input",
                    "hardware_ref": "sim_2",
                    "description": "Analog input"
                },
                {
                    "name": "analog_out",
                    "io_type": "analog_output",
                    "hardware_ref": "sim_3",
                    "description": "Analog output"
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_add_backend(self, manager_with_backend):
        """Test adding a backend"""
        manager = manager_with_backend
        assert "simulator" in manager.backends
        assert isinstance(manager.backends["simulator"], SimulatedBackend)
    
    @pytest.mark.asyncio
    async def test_configure_from_dict(self, manager_with_backend, sample_config):
        """Test configuration from dictionary"""
        manager = manager_with_backend
        
        # Configure manager
        success = await manager.configure_from_dict(sample_config)
        assert success
        
        # Verify points were configured
        assert len(manager.points) == 4
        assert "digital_in" in manager.points
        assert "digital_out" in manager.points
        assert "analog_in" in manager.points
        assert "analog_out" in manager.points
        
        # Verify critical points
        assert "digital_in" in manager.critical_points
    
    @pytest.mark.asyncio
    async def test_start_stop(self, manager_with_backend, sample_config):
        """Test starting and stopping the manager"""
        manager = manager_with_backend
        await manager.configure_from_dict(sample_config)
        
        # Start manager
        await manager.start()
        assert manager._running
        assert manager._polling_task is not None
        
        # Stop manager
        await manager.stop()
        assert not manager._running
        assert manager._polling_task is None
    
    @pytest.mark.asyncio
    async def test_write_read(self, manager_with_backend, sample_config):
        """Test writing and reading points"""
        manager = manager_with_backend
        await manager.configure_from_dict(sample_config)
        await manager.start()
        
        try:
            # Write to output
            success = await manager.write("digital_out", True)
            assert success
            
            # Read back
            value = await manager.read("digital_out")
            assert value is True
            
            # Write to analog output
            success = await manager.write("analog_out", 3.14)
            assert success
            
            # Read back
            value = await manager.read("analog_out")
            assert value == 3.14
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_read_all(self, manager_with_backend, sample_config):
        """Test reading all points"""
        manager = manager_with_backend
        await manager.configure_from_dict(sample_config)
        await manager.start()
        
        try:
            # Write some values
            await manager.write("digital_out", True)
            await manager.write("analog_out", 3.14)
            
            # Read all points
            states = await manager.read_all()
            
            # Verify results
            assert isinstance(states, dict)
            assert "digital_out" in states
            assert "analog_out" in states
            assert states["digital_out"] is True
            assert states["analog_out"] == 3.14
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_change_callbacks(self, manager_with_backend, sample_config):
        """Test state change callbacks"""
        manager = manager_with_backend
        await manager.configure_from_dict(sample_config)
        
        changes_received = []
        
        def change_callback(changes):
            changes_received.extend(changes)
        
        manager.on_change(change_callback)
        await manager.start()
        
        try:
            # Write to output
            await manager.write("digital_out", True)
            
            # Wait for callback
            await asyncio.sleep(0.1)
            
            # Verify callback was called
            assert len(changes_received) == 1
            change = changes_received[0]
            assert isinstance(change, StateChange)
            assert change.point_name == "digital_out"
            assert change.old_value is False
            assert change.new_value is True
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_invalid_operations(self, manager_with_backend):
        """Test invalid operations"""
        manager = manager_with_backend
        
        # Try to read before configuration
        with pytest.raises(RuntimeError):
            await manager.read("test_point")
        
        # Try to write before configuration
        with pytest.raises(RuntimeError):
            await manager.write("test_point", True)
    
    @pytest.mark.asyncio
    async def test_performance_metrics(self, manager_with_backend, sample_config):
        """Test performance metrics"""
        manager = manager_with_backend
        await manager.configure_from_dict(sample_config)
        await manager.start()
        
        try:
            # Perform some operations
            await manager.write("digital_out", True)
            await manager.read("digital_out")
            
            # Get metrics
            metrics = await manager.metrics.get_metrics()
            
            # Verify metrics
            assert "simulator" in metrics
            backend_metrics = metrics["simulator"]
            assert backend_metrics["read"]["count"] > 0
            assert backend_metrics["write"]["count"] > 0
            assert "avg_time" in backend_metrics["read"]
            assert "avg_time" in backend_metrics["write"]
            
        finally:
            await manager.stop()

class TestAsyncBehavior:
    """Test async behavior and performance"""
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent operations"""
        manager = IoManager()
        backend = SimulatedBackend()
        await manager.add_backend("simulator", backend)
        
        config = {
            "io_points": [
                {
                    "name": f"point_{i}",
                    "io_type": "digital_output",
                    "hardware_ref": f"sim_{i}"
                }
                for i in range(10)
            ]
        }
        
        await manager.configure_from_dict(config)
        await manager.start()
        
        try:
            # Perform concurrent writes
            write_tasks = [
                manager.write(f"point_{i}", i % 2 == 0)
                for i in range(10)
            ]
            await asyncio.gather(*write_tasks)
            
            # Perform concurrent reads
            read_tasks = [
                manager.read(f"point_{i}")
                for i in range(10)
            ]
            results = await asyncio.gather(*read_tasks)
            
            # Verify results
            for i, result in enumerate(results):
                assert result == (i % 2 == 0)
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    async def test_polling_performance(self):
        """Test polling performance"""
        manager = IoManager(PollingConfig(
            normal_interval=0.01,  # 10ms
            critical_interval=0.001,  # 1ms
            batch_size=16,
            batch_timeout=0.001  # 1ms
        ))
        
        backend = SimulatedBackend()
        await manager.add_backend("simulator", backend)
        
        config = {
            "io_points": [
                {
                    "name": "critical_in",
                    "io_type": "digital_input",
                    "hardware_ref": "sim_0",
                    "critical": True
                },
                {
                    "name": "normal_in",
                    "io_type": "digital_input",
                    "hardware_ref": "sim_1"
                }
            ]
        }
        
        await manager.configure_from_dict(config)
        
        # Track changes
        changes_received = []
        
        def change_callback(changes):
            changes_received.extend(changes)
        
        manager.on_change(change_callback)
        await manager.start()
        
        try:
            # Simulate some changes
            backend.set_simulated_states({"sim_0": True})
            await asyncio.sleep(0.002)  # Wait for critical poll
            
            backend.set_simulated_states({"sim_1": True})
            await asyncio.sleep(0.02)  # Wait for normal poll
            
            # Verify changes were detected
            assert len(changes_received) == 2
            
            # Verify critical point was updated first
            assert changes_received[0].point_name == "critical_in"
            assert changes_received[1].point_name == "normal_in"
            
        finally:
            await manager.stop()

@pytest.mark.asyncio
async def test_integration_example():
    """Integration test example"""
    # Create manager with custom polling config
    manager = IoManager(PollingConfig(
        normal_interval=0.01,
        critical_interval=0.001,
        batch_size=16,
        batch_timeout=0.001
    ))
    
    # Add simulated backend
    backend = SimulatedBackend()
    await manager.add_backend("simulator", backend)
    
    # Configure I/O points
    config = {
        "io_points": [
            {
                "name": "emergency_stop",
                "io_type": "digital_input",
                "hardware_ref": "sim_0",
                "critical": True,
                "description": "Emergency stop button"
            },
            {
                "name": "motor_enable",
                "io_type": "digital_output",
                "hardware_ref": "sim_1",
                "description": "Motor enable signal"
            },
            {
                "name": "speed_setpoint",
                "io_type": "analog_output",
                "hardware_ref": "sim_2",
                "description": "Motor speed setpoint"
            }
        ]
    }
    
    # Configure manager
    await manager.configure_from_dict(config)
    
    # Track state changes
    changes_received = []
    
    def change_callback(changes):
        changes_received.extend(changes)
    
    manager.on_change(change_callback)
    
    # Start manager
    await manager.start()
    
    try:
        # Simulate emergency stop
        backend.set_simulated_states({"sim_0": True})
        await asyncio.sleep(0.002)  # Wait for critical poll
        
        # Verify emergency stop was detected
        assert len(changes_received) == 1
        assert changes_received[0].point_name == "emergency_stop"
        assert changes_received[0].new_value is True
        
        # Enable motor
        await manager.write("motor_enable", True)
        await asyncio.sleep(0.01)
        
        # Set speed
        await manager.write("speed_setpoint", 75.5)
        await asyncio.sleep(0.01)
        
        # Read current state
        states = await manager.read_all()
        assert states["motor_enable"] is True
        assert states["speed_setpoint"] == 75.5
        
    finally:
        await manager.stop()