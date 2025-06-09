# IoControl

High-performance asynchronous I/O control for embedded systems.

## Overview

IoControl is a Python package designed for high-performance I/O control in embedded systems. It provides an asynchronous interface for managing digital and analog I/O points, with support for both simulated and hardware backends.

## Features

- Asynchronous I/O operations using Python's asyncio
- Support for digital and analog I/O points
- Configurable polling intervals for critical and non-critical points
- Performance metrics tracking
- Simulated backend for testing
- Support for hardware backends (MCP expander support planned)
- Change notification system
- YAML/JSON configuration support

## Installation

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package
pip install -e .

# Install optional dependencies
pip install -e ".[hardware]"  # For hardware support
pip install -e ".[simulation]"  # For simulation features
pip install -e ".[dev]"  # For development tools
```

## Quick Start

```python
import asyncio
from iocontrol import IoManager, IoPoint, IoType, SimulatedBackend

async def main():
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
                "description": "Test relay"
            }
        ]
    }
    
    # Initialize system
    await manager.configure_from_dict(config)
    await manager.start()
    
    # Use the system
    await manager.write("relay_1", True)
    state = await manager.read("relay_1")
    
    # Clean shutdown
    await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

I/O points can be configured using either a dictionary or a YAML/JSON file:

```yaml
io_points:
  - name: relay_1
    io_type: digital_output
    hardware_ref: sim.pin0
    critical: false
    description: Test relay
  - name: sensor_1
    io_type: digital_input
    hardware_ref: sim.pin1
    critical: true
    description: Test sensor
```

## Development

### Requirements
- Python 3.11 or higher
- Development dependencies (see pyproject.toml)

### Testing
```bash
pytest
```

### Code Style
The project uses:
- Black for code formatting
- Ruff for linting
- MyPy for type checking

## License

MIT License - See LICENSE file for details

## Author

Landon Bell (landon.bell@valorence.com)

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request
