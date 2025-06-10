"""
Enhanced configuration example for IoControl package
This shows runtime configuration management with validation
"""

import asyncio
import logging
from pathlib import Path
from iocontrol import IoManager, SimulatedBackend
from iocontrol.config import RuntimeConfigManager
from iocontrol.validation import add_validation_to_manager, validate_io_config, print_validation_results

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
    """Demonstrate runtime configuration management with validation"""
    
    print("IoControl Configuration Management with Validation Demo")
    print("=" * 60)
    
    # Create IoManager and backend
    manager = IoManager()
    simulator = SimulatedBackend("test_sim")
    await manager.add_backend("simulator", simulator)
    
    # Add validation to the manager
    print("\nAdding validation to IoManager...")
    add_validation_to_manager(manager)
    print("Validation enabled - all configurations will be automatically validated")
    
    # Create runtime config manager
    config_manager = RuntimeConfigManager()
    
    # Register for config changes
    config_manager.on_config_change(config_change_handler)
    
    # Test configuration validation first
    print("\n" + "=" * 60)
    print("TESTING CONFIGURATION VALIDATION")
    print("=" * 60)
    
    # Test 1: Valid configuration
    print("\n1. Testing VALID configuration:")
    print("-" * 30)
    
    valid_config = {
        "io_points": [
            {
                "name": "pump_main",
                "io_type": "digital_output",
                "hardware_ref": "sim.pin0",
                "critical": True,
                "initial_state": False,
                "description": "Main water pump relay"
            },
            {
                "name": "emergency_stop",
                "io_type": "digital_input", 
                "hardware_ref": "sim.pin1",
                "critical": True,
                "pull_up": True,
                "description": "Emergency stop button (NC contact)"
            },
            {
                "name": "level_sensor",
                "io_type": "analog_input",
                "hardware_ref": "sim.analog0",
                "description": "Water level sensor (0-100%)"
            }
        ]
    }
    
    is_valid, issues = validate_io_config(valid_config)
    print_validation_results(issues, show_info=True)
    
    # Test 2: Invalid configuration
    print("\n2. Testing INVALID configuration:")
    print("-" * 30)
    
    invalid_config = {
        "io_points": [
            {
                "name": "123_bad_name",  # Invalid name (starts with number)
                "io_type": "invalid_type",  # Invalid io_type
                "hardware_ref": "sim.pin0"
            },
            {
                "name": "pump_main",  # Duplicate name
                "io_type": "digital_output", 
                "hardware_ref": "sim.pin0",  # Duplicate hardware_ref
                "initial_state": "not_boolean"  # Wrong type for digital
            },
            {
                # Missing required fields
                "description": "Incomplete point"
            }
        ]
    }
    
    is_valid, issues = validate_io_config(invalid_config)
    print_validation_results(issues, show_info=False)
    
    # Test 3: Configuration with warnings
    print("\n3. Testing configuration with WARNINGS:")
    print("-" * 30)
    
    warning_config = {
        "io_points": [
            {
                "name": "emergency_stop",
                "io_type": "digital_output",  # Should be input
                "hardware_ref": "sim.pin0",
                "critical": False,  # Should be critical
                "description": "Emergency stop (misconfigured)"
            },
            {
                "name": "critical_pump",
                "io_type": "digital_output",
                "hardware_ref": "sim.pin1",
                "critical": True
                # Missing initial_state for critical output
            },
            {
                "name": "temp_input",
                "io_type": "digital_input",
                "hardware_ref": "sim.pin2",
                "initial_state": True  # Inputs don't need initial_state
            }
        ]
    }
    
    is_valid, issues = validate_io_config(warning_config)
    print_validation_results(issues, show_info=True)
    
    # Now test with IoManager integration
    print("\n" + "=" * 60)
    print("TESTING IOMANAGER INTEGRATION")
    print("=" * 60)
    
    print("\n4. Configuring IoManager with VALID configuration:")
    print("-" * 40)
    success = await manager.configure_from_dict(valid_config)
    print(f"Configuration result: {'Success' if success else 'Failed'}")
    
    if success:
        # Load config into config manager
        config_manager.current_config = valid_config
        
        # Start the system
        await manager.start()
        print("IoManager started successfully")
        
        try:
            print("\n5. Testing runtime configuration changes:")
            print("-" * 40)
            
            # Add a new I/O point at runtime
            new_point = {
                "name": "status_led",
                "io_type": "digital_output", 
                "hardware_ref": "sim.pin2",
                "initial_state": False,
                "description": "System status LED"
            }
            
            # Validate the new point first
            temp_config = {
                "io_points": valid_config["io_points"] + [new_point]
            }
            is_valid, issues = validate_io_config(temp_config)
            
            if is_valid:
                success = await config_manager.add_io_point(new_point, user="admin")
                print(f"Add new point: {'Success' if success else 'Failed'}")
            else:
                print("New point validation failed:")
                print_validation_results(issues)
            
            # Try to add an invalid point
            print("\n6. Testing invalid runtime addition:")
            print("-" * 40)
            
            invalid_point = {
                "name": "pump_main",  # Duplicate name
                "io_type": "digital_output",
                "hardware_ref": "sim.pin0"  # Duplicate hardware_ref
            }
            
            # This should fail validation
            temp_config = {
                "io_points": config_manager.current_config["io_points"] + [invalid_point]
            }
            is_valid, issues = validate_io_config(temp_config)
            print("Attempting to add invalid point:")
            print_validation_results(issues, show_info=False)
            
            if not is_valid:
                print("Addition blocked by validation (as expected)")
            
            # Modify existing point
            print("\n7. Testing point modification:")
            print("-" * 40)
            
            modified_point = {
                "name": "pump_main",
                "io_type": "digital_output",
                "hardware_ref": "sim.pin0", 
                "critical": True,
                "initial_state": False,
                "description": "Main water pump (updated description)"
            }
            
            success = await config_manager.modify_io_point("pump_main", modified_point, user="admin")
            print(f"Modify point: {'Success' if success else 'Failed'}")
            
            # Save configuration to file
            config_path = Path("validated_config.yaml")
            success = await config_manager.save_config(config_path)
            print(f"Save config: {'Success' if success else 'Failed'}")
            
            if config_path.exists():
                print(f"Configuration saved to: {config_path.absolute()}")
                
                # Test file validation
                print("\n8. Testing saved file validation:")
                print("-" * 40)
                is_valid = manager.validate_config_file(str(config_path))
                print(f"Saved file validation: {'Passed' if is_valid else 'Failed'}")
            
            # Show configuration history
            print("\n9. Configuration change history:")
            print("-" * 40)
            history = config_manager.get_config_history()
            for i, snapshot in enumerate(history):
                print(f"Version {snapshot.version}: {snapshot.timestamp}")
                for change in snapshot.changes_since_last:
                    print(f"  - {change.change_type}: {change.point_name}")
            
            # Test rollback (if we have history)
            if len(history) > 1:
                print(f"\n10. Testing configuration rollback:")
                print("-" * 40)
                target_version = history[0].version
                success = await config_manager.rollback_to_version(target_version)
                print(f"Rollback to version {target_version}: {'Success' if success else 'Failed'}")
                
                # Validate after rollback
                current_config = config_manager.current_config
                is_valid, issues = validate_io_config(current_config)
                print(f"Post-rollback validation: {'Passed' if is_valid else 'Failed'}")
                if issues:
                    print(f"Issues found: {len(issues)}")
            
            # Test some I/O operations
            print("\n11. Testing I/O operations:")
            print("-" * 40)
            
            await manager.write("pump_main", True)
            pump_state = await manager.read("pump_main")
            print(f"Pump control test: {pump_state}")
            
            all_states = await manager.read_all()
            print(f"Total I/O points active: {len(all_states)}")
            
        finally:
            await manager.stop()
            print("IoManager stopped")
    
    else:
        print("Configuration failed - cannot proceed with demo")
    
    # Test invalid configuration with IoManager
    print("\n12. Testing IoManager with INVALID configuration:")
    print("-" * 50)
    
    print("Attempting to configure IoManager with invalid config...")
    success = await manager.configure_from_dict(invalid_config)
    print(f"Result: {'Success' if success else 'Failed (expected)'}")
    
    print("\nConfiguration demo completed")
    print("\nKey takeaways:")
    print("- All configurations are automatically validated")
    print("- Invalid configurations are rejected before they can cause problems")
    print("- Warnings help you improve configuration safety")
    print("- Runtime changes are also validated")
    print("- Configuration history is maintained for rollback")


def create_example_configs_with_validation():
    """Create example configuration files and validate them"""
    
    print("\n" + "=" * 60)
    print("CREATING AND VALIDATING EXAMPLE CONFIGURATIONS")
    print("=" * 60)
    
    configs_dir = Path("examples/configs")
    configs_dir.mkdir(parents=True, exist_ok=True)
    
    # Test each example configuration
    example_files = [
        "simple.yaml",
        "simple.json", 
        "industrial.yaml",
        "safety.yaml",
        "virtual.json"
    ]
    
    for filename in example_files:
        config_file = configs_dir / filename
        if config_file.exists():
            print(f"\nValidating {filename}:")
            print("-" * 30)
            
            try:
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    import yaml
                    with open(config_file, 'r') as f:
                        config = yaml.safe_load(f)
                else:
                    import json
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                
                is_valid, issues = validate_io_config(config)
                print_validation_results(issues, show_info=True)
                
            except Exception as e:
                print(f"Error loading {filename}: {e}")
        else:
            print(f"\nSkipping {filename} - file not found")


if __name__ == "__main__":
    print("IoControl Configuration Validation Demo")
    print("This demonstrates configuration validation and safety checks")
    print()
    
    # Run the main demo
    asyncio.run(main())
    
    # Test example configurations
    create_example_configs_with_validation()