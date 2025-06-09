"""
Example configuration file for IoControl package
This shows how to set up runtime configuration management
"""

import asyncio
import logging
from pathlib import Path
from iocontrol import IoManager, SimulatedBackend
from iocontrol.config import RuntimeConfigManager

# Enable logging
logging.basicConfig(level=logging.INFO)

async def config_change_handler(changes):
    """Handle configuration changes"""
    for change in changes:
        print(f"Config change: {change.change_type} - {change.point_name}")
        if change.change_type == 'add':
            print(f"  Added: {change.new_config}")
        elif change.change_type == 'remove':
            print(f"  Removed: {change.old_config}")
        elif change.change_type == 'modify':
            print(f"  Modified: {change.old_config} -> {change.new_config}")

async def main():
    """Demonstrate runtime configuration management"""
    
    # Create IoManager and backend
    manager = IoManager()
    simulator = SimulatedBackend("test_sim")
    await manager.add_backend("simulator", simulator)
    
    # Create runtime config manager
    config_manager = RuntimeConfigManager()
    
    # Register for config changes
    config_manager.on_config_change(config_change_handler)
    
    # Initial configuration
    initial_config = {
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
            }
        ]
    }
    
    # Configure from dictionary
    success = await manager.configure_from_dict(initial_config)
    print(f"Initial configuration: {'Success' if success else 'Failed'}")
    
    # Load config into config manager
    config_manager.current_config = initial_config
    
    # Start the system
    await manager.start()
    
    print("\n=== Testing Runtime Configuration Changes ===")
    
    # Add a new I/O point at runtime
    new_point = {
        "name": "emergency_stop",
        "io_type": "digital_input", 
        "hardware_ref": "sim.pin2",
        "critical": True,
        "description": "Emergency stop button"
    }
    
    success = await config_manager.add_io_point(new_point, user="admin")
    print(f"Add new point: {'Success' if success else 'Failed'}")
    
    # Modify existing point
    modified_point = {
        "name": "relay_1",
        "io_type": "digital_output",
        "hardware_ref": "sim.pin0", 
        "critical": True,  # Changed from False
        "description": "Critical test relay"  # Updated description
    }
    
    success = await config_manager.modify_io_point("relay_1", modified_point, user="admin")
    print(f"Modify point: {'Success' if success else 'Failed'}")
    
    # Save configuration to file
    config_path = Path("runtime_config.yaml")
    success = await config_manager.save_config(config_path)
    print(f"Save config: {'Success' if success else 'Failed'}")
    
    # Show configuration history
    print("\n=== Configuration History ===")
    history = config_manager.get_config_history()
    for i, snapshot in enumerate(history):
        print(f"Version {snapshot.version}: {snapshot.timestamp}")
        for change in snapshot.changes_since_last:
            print(f"  - {change.change_type}: {change.point_name}")
    
    # Test rollback (if we have history)
    if len(history) > 1:
        print(f"\n=== Testing Rollback ===")
        target_version = history[0].version
        success = await config_manager.rollback_to_version(target_version)
        print(f"Rollback to version {target_version}: {'Success' if success else 'Failed'}")
    
    # Test file watching (would normally run continuously)
    print(f"\n=== File Watching Demo ===")
    await config_manager.start_file_watching()
    print("Started file watching (modify runtime_config.yaml to see changes)")
    
    # Run for a few seconds to demonstrate
    await asyncio.sleep(3)
    
    # Clean shutdown
    await config_manager.stop_file_watching()
    await manager.stop()
    
    print("\nConfiguration demo completed")

if __name__ == "__main__":
    asyncio.run(main())