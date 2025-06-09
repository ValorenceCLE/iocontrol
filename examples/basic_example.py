import asyncio
import logging
from iocontrol import IoManager, IoPoint, IoType, SimulatedBackend

# Enable logging to see what's happening
logging.basicConfig(level=logging.INFO)

async def main():
    """Test the IoControl package"""
    print("Testing IoControl Package")

    # Create IoManager
    manager = IoManager()

    # Add simulated backend
    simulator = SimulatedBackend("test_sim")
    await manager.add_backend("simulator", simulator)

    # Configure I/O points
    config = {
        "io_points": [
            {
                "name": "relay_1",
                "io_type": "digital_output", 
                "hardware_ref": "sim.pin0",
                "critical": False,
                "description": "Test relay"
            },
            {
                "name": "sensor_1",
                "io_type": "digital_input",
                "hardware_ref": "sim.pin1", 
                "critical": True,
                "description": "Test sensor"
            },
            {
                "name": "emergency_stop",
                "io_type": "digital_input",
                "hardware_ref": "sim.pin2",
                "critical": True,
                "description": "Emergency stop button"
            }
        ]
    }

    success = await manager.configure_from_dict(config)
    print(f"Configuration: {'Success' if success else 'Failed'}")

    # Setup change monitoring
    def on_io_change(changes):
        for change in changes:
            print(f"Change: {change.point_name} {change.old_value} -> {change.new_value}")
    
    manager.on_change(on_io_change)

    # Start the I/O manager
    await manager.start()
    print("I/O manager started")

    # Test Operations - New API
    print("\n Testing I/O Operations...")

    # Write to relay 
    success = await manager.write("relay_1", True)
    print(f"Relay Control: {'Success' if success else 'Failed'}")

    # Read relay state
    state = await manager.read("relay_1")
    print(f"Relay State: {state}")

    # Read all relay states
    state = await manager.read_all()
    print(f"All States: {state}")

    # Simulate input change
    print("\n Simulating input change...")
    simulator.simulate_input_change("sensor_1", True)
    simulator.simulate_input_change("emergency_stop", True)

    # Wait for polling to detect changes
    await asyncio.sleep(0.1)

    # Check performance metrics
    print("\n Performance Metrics:")
    print(f"Reads: {manager.metrics.read_count}")
    print(f"Writes: {manager.metrics.write_count}")
    print(f"Avg Read Time: {manager.metrics.avg_read_time_ms:.2f}ms")
    print(f"Avg Write Time: {manager.metrics.avg_write_time_ms:.2f}ms")
    print(f"Errors: {manager.metrics.error_count}")
    
    # Test rapid operations (performance test)
    print("\n Testing Rapid Operations...")
    start_time = asyncio.get_event_loop().time()

    for i in range(1000):
        await manager.write("relay_1", i % 2 == 0)
        state = await manager.read("relay_1")
    
    end_time = asyncio.get_event_loop().time()
    total_time_ms = (end_time - start_time) * 1000
    ops_per_second = 2000 / (total_time_ms / 1000)

    print(f"2000 operations in {total_time_ms:.2f}ms ({ops_per_second:.1f} ops/sec)")

    # Keep running for a bit to see polling in action
    print("\n Running for 5 seconds to see polling...")
    await asyncio.sleep(5)

    # Clean shutdown
    await manager.stop()
    print("I/O manager stopped")

if __name__ == "__main__":
    asyncio.run(main())
