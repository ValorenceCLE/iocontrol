"""Core IoManager Implementation"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable, Union
from pathlib import Path
import json

from .types import IoPoint, IoType, StateChange, PerformanceMetrics
from .backends import HardwareBackend, SimulatedBackend

logger = logging.getLogger(__name__)

class IoManager:
    """
    High-Performance async I/O manager

    This is the main class for managing I/O operations.

    #! THIS WILL REPLACE CURRENT CELERY TASKS
    """
    def __init__(self):
        self.backends: Dict[str, HardwareBackend] = {}
        self.points: Dict[str, IoPoint] = {}
        self.current_states: Dict[str, Any] = {}
        self.change_callbacks: List[Callable] = []

        # Performance Settings
        self.polling_interval = 0.01 # 10ms polling interval
        self.critical_polling_interval = 0.001 # 1ms critical polling interval
        self.critical_points: set = set()

        # Runtime control
        self._running = False
        self._polling_task: Optional[asyncio.Task] = None

        # Metrics
        self.metrics = PerformanceMetrics()

    async def add_backend(self, name: str, backend: HardwareBackend) -> None:
        """Add a new hardware backend"""
        self.backends[name] = backend
        logger.info(f"Added backend: {name}")

    async def configure_from_dict(self, config: Dict[str, Any]) -> bool:
        "Configure IoManager from a dictionary"
        try:
            # Create I/O points
            points = []
            for point_config in config.get('io_points', []):
                point = IoPoint(
                    name=point_config['name'],
                    io_type=IoType(point_config['io_type']),
                    hardware_ref=point_config['hardware_ref'],
                    critical=point_config.get('critical', False),
                    interrupt_enabled=point_config.get('interrupt_enabled', False),
                    pull_up=point_config.get('pull_up', False),
                    description=point_config.get('description', '')
                )
                points.append(point)

                if point.critical:
                    self.critical_points.add(point.name)
            self.points = {point.name: point for point in points}

            # Initialize Backends
            for backend in self.backends.values():
                backend_points = [p for p in points if self._get_backend_for_point(p) == backend]
                if backend_points:
                    await backend.initialize(backend_points)
            
            logger.info(f"Configured {len(self.points)} I/O points")
            return True
        
        except Exception as e:
            logger.error(f"Configuration failed: {e}")
            return False
    
    async def configure_from_file(self, config_path: Union[str, Path]) -> bool:
        """Configure from JSON/YAML file"""
        try:
            path = Path(config_path)
            with open(path, 'r') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    import yaml
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)
            
            return await self.configure_from_dict(config)
        except Exception as e:
            logger.error(f"Failed to load configuration from {config_path}: {e}")
            return False

    async def start(self) -> None:
        """Start the I/O manager system"""
        if self._running:
            return
        self._running = True
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("I/O manager started")

    async def stop(self) -> None:
        """Stop the I/O system."""
        self._running = False
        
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        # Close backends
        for backend in self.backends.values():
            await backend.close()

        logger.info("IoManager stopped")

    #! Main API Methods - these will be the main entry points for the I/O system
    #? INFO: This replaces my current celery tasks in the "https://github.com/ValorenceCLE/Backend" repo

    async def read(self, point_name: str) -> Any:
        """Read a single I/O point (Replaces celery tasks)"""
        start_time = time.perf_counter()

        try:
            # Return cached value if available
            if point_name in self.current_states:
                result = self.current_states[point_name]
            else:
                # Fallback: Read from hardware (backend)
                point = self.points.get(point_name)
                if not point:
                    raise ValueError(f"Unknown I/O point: {point_name}")
                
                backend = self._get_backend_for_point(point)
                if not backend:
                    raise ValueError(f"No backend for point: {point_name}")
                
                data = await backend.read_all()
                result = data.get(point_name)
                self.current_states[point_name] = result
            
            # Update metrics
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.update_read_time(duration_ms)

            return result
        
        except Exception as e:
            logger.error(f"Failed to read point {point_name}: {e}")
            raise
        
    async def write(self, point_name: str, value: Any) -> bool:
        """Write to a single I/O point (Replaces celery tasks)"""
        start_time = time.perf_counter()
        
        try:
            point = self.points.get(point_name)
            if not point:
                raise ValueError(f"Unknown I/O point: {point_name}")
            
            if point.io_type not in [IoType.DIGITAL_OUTPUT, IoType.ANALOG_OUTPUT]:
                raise ValueError(f"Point {point_name} is not writable")
            
            backend = self._get_backend_for_point(point)
            if not backend:
                raise ValueError(f"No backend for point: {point_name}")
            
            success = await backend.write_point(point_name, value)

            if success:
                old_value = self.current_states.get(point_name)
                self.current_states[point_name] = value

                # Notify callbacks of change
                if old_value != value:
                    change = StateChange.create(
                        point_name=point_name,
                        old_value=old_value,
                        new_value=value,
                        hardware_ref=point.hardware_ref
                    )
                    await self._notify_changes([change])

            # Update metrics
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.update_write_time(duration_ms)
            return success
        
        except Exception as e:
            logger.error(f"Write failed for {point_name}: {e}")
            self.metrics.error_count += 1
            return False
    
    async def read_all(self) -> Dict[str, Any]:
        """Read all I/O points (Replaces celery tasks)"""
        return self.current_states.copy()
    
    def on_change(self, callback: Callable[[List[StateChange]], None]) -> None:
        """Register a callback for I/O state changes"""
        self.change_callbacks.append(callback)

    # Internal Methods
    async def _polling_loop(self) -> None:
        """Main polling loop"""
        last_critical_poll = 0
        last_normal_poll = 0

        while self._running:
            try:
                current_time = time.time()

                # Poll critical points more frequently
                if (current_time - last_critical_poll) >= self.critical_polling_interval:
                    if self.critical_points:
                        await self._poll_critical_points()
                    last_critical_poll = current_time
                
                # Poll all poiints at normal interval
                if (current_time - last_normal_poll) >= self.polling_interval:
                    await self._poll_all_points()
                    last_normal_poll = current_time
                
                await asyncio.sleep(0.001) # 1ms sleep
            
            except asyncio.CancelledError:
                logger.info("Polling loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(self.polling_interval)
        
    async def _poll_critical_points(self) -> None:
        """Fast polling for critical points."""
        # TODO: Implement critical-only polling
        pass

    async def _poll_all_points(self) -> None:
        """Poll all I/O points and detect changes"""
        try:
            changes = []
            new_states = {}

            # Read all backends concurrently
            tasks = []
            for backend in self.backends.values():
                tasks.append(backend.read_all())
            
            # Wait for all reads to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Combine results
            for result in results:
                if isinstance(result, Exception):
                    continue
                new_states.update(result)

            # Detect changes
            for point_name, new_value in new_states.items():
                old_value = self.current_states.get(point_name)
                if old_value != new_value:
                    point = self.points.get(point_name)
                    if point:
                        change = StateChange.create(
                            point_name=point_name,
                            old_value=old_value,
                            new_value=new_value,
                            hardware_ref=point.hardware_ref
                        )
                        changes.append(change)
            
            # Update State
            self.current_states.update(new_states)

            # Notify callbacks of changes
            if changes:
                await self._notify_changes(changes)
        
        except Exception as e:
            logger.error(f"Error polling all points: {e}")
    
    async def _notify_changes(self, changes: List[StateChange]) -> None:
        """Notify all registered callbacks about state changes"""
        for callback in self.change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(changes)
                else:
                    await asyncio.to_thread(callback, changes)
            except Exception as e:
                logger.error(f"Error in change callback: {e}")
    
    def _get_backend_for_point(self, point: IoPoint) -> Optional[HardwareBackend]:
        """Get backend for I/O point"""
        # Simple mapping for now
        # TODO: Improve this later
        if point.hardware_ref.startswith('sim'):
            return self.backends.get('simulator')
        elif point.hardware_ref.startswith('mcp'):
            return self.backends.get('mcp')
        return None