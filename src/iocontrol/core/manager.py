"""High-performance async I/O manager implementation"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field

from ..types import IoPoint, IoType, StateChange
from ..backends.base import HardwareBackend
from .metrics import PerformanceMonitor
from iocontrol.backends import MCPBackend, MCP23017Config

logger = logging.getLogger(__name__)

@dataclass
class PollingConfig:
    """Configuration for polling behavior"""
    normal_interval: float = 0.01  # 10ms
    critical_interval: float = 0.001  # 1ms
    batch_size: int = 16
    batch_timeout: float = 0.001  # 1ms

class IoManager:
    """High-performance async I/O manager"""
    
    def __init__(self, polling_config: Optional[PollingConfig] = None):
        self.backends: Dict[str, HardwareBackend] = {}
        self.points: Dict[str, IoPoint] = {}
        self.current_states: Dict[str, Any] = {}
        self.change_callbacks: List[Callable[[List[StateChange]], None]] = []
        self.critical_points: Set[str] = set()
        
        # Performance monitoring
        self.metrics = PerformanceMonitor()
        
        # Polling configuration
        self.polling_config = polling_config or PollingConfig()
        
        # Runtime control
        self._running = False
        self._polling_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._batch_lock = asyncio.Lock()
        self._pending_writes: Dict[str, Any] = {}
    
    async def add_backend(self, name: str, backend: HardwareBackend) -> None:
        """Add a new hardware backend"""
        async with self._lock:
            self.backends[name] = backend
            logger.info(f"Added backend: {name}")
    
    async def configure_from_dict(self, config: Dict[str, Any]) -> bool:
        """Configure IoManager from a dictionary"""
        try:
            async with self._lock:
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
                
                # Initialize backends
                init_tasks = []
                for backend in self.backends.values():
                    backend_points = [p for p in points if self._get_backend_for_point(p) == backend]
                    if backend_points:
                        init_tasks.append(backend.initialize(backend_points))
                
                # Wait for all backends to initialize
                await asyncio.gather(*init_tasks)
                
                # Initialize states
                await self._initialize_states()
                
                logger.info(f"Configured {len(self.points)} I/O points")
                return True
        
        except Exception as e:
            logger.error(f"Configuration failed: {e}")
            return False
    
    async def _initialize_states(self) -> None:
        """Initialize current_states with all I/O points"""
        async with self._state_lock:
            # Read initial states from all backends in parallel
            read_tasks = []
            for backend in self.backends.values():
                read_tasks.append(backend.read_all())
            
            results = await asyncio.gather(*read_tasks, return_exceptions=True)
            
            # Combine results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Failed to read initial states: {result}")
                    continue
                self.current_states.update(result)
            
            # Set defaults for any missing points
            for point_name, point in self.points.items():
                if point_name not in self.current_states:
                    self.current_states[point_name] = False
    
    async def start(self) -> None:
        """Start the I/O manager system"""
        if self._running:
            return
        
        self._running = True
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("I/O manager started")
    
    async def stop(self) -> None:
        """Stop the I/O system"""
        self._running = False
        
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None
        
        # Close all backends
        close_tasks = [backend.close() for backend in self.backends.values()]
        await asyncio.gather(*close_tasks)
        
        logger.info("I/O manager stopped")
    
    async def read(self, point_name: str) -> Any:
        """Read a single I/O point"""
        start_time = time.perf_counter()
        
        try:
            async with self._state_lock:
                # Return cached value if available
                if point_name in self.current_states:
                    result = self.current_states[point_name]
                else:
                    # Fallback: Read from hardware
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
            await self.metrics.record_operation(
                backend_name=self._get_backend_name_for_point(point_name),
                operation='read',
                duration=duration_ms
            )
            
            return result
        
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self.metrics.record_operation(
                backend_name=self._get_backend_name_for_point(point_name),
                operation='read',
                duration=duration_ms,
                error=True
            )
            logger.error(f"Failed to read point {point_name}: {e}")
            raise
    
    async def write(self, point_name: str, value: Any) -> bool:
        """Write to a single I/O point"""
        start_time = time.perf_counter()
        
        try:
            point = self.points.get(point_name)
            if not point:
                raise ValueError(f"Unknown I/O point: {point_name}")
            
            if point.io_type not in [IoType.DIGITAL_OUTPUT, IoType.ANALOG_OUTPUT]:
                raise ValueError(f"Point {point_name} is not writable")
            
            # Add to pending writes
            async with self._batch_lock:
                self._pending_writes[point_name] = value
            
            # Update local state
            async with self._state_lock:
                old_value = self.current_states.get(point_name)
                self.current_states[point_name] = value
            
            # Notify callbacks if value changed
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
            await self.metrics.record_operation(
                backend_name=self._get_backend_name_for_point(point_name),
                operation='write',
                duration=duration_ms
            )
            
            return True
        
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self.metrics.record_operation(
                backend_name=self._get_backend_name_for_point(point_name),
                operation='write',
                duration=duration_ms,
                error=True
            )
            logger.error(f"Write failed for {point_name}: {e}")
            return False
    
    async def read_all(self) -> Dict[str, Any]:
        """Read all I/O points"""
        async with self._state_lock:
            return self.current_states.copy()
    
    def on_change(self, callback: Callable[[List[StateChange]], None]) -> None:
        """Register a callback for I/O state changes"""
        self.change_callbacks.append(callback)
    
    async def _polling_loop(self) -> None:
        """Main polling loop"""
        last_critical_poll = 0
        last_normal_poll = 0
        
        while self._running:
            try:
                current_time = time.time()
                
                # Poll critical points more frequently
                if (current_time - last_critical_poll) >= self.polling_config.critical_interval:
                    if self.critical_points:
                        await self._poll_critical_points()
                    last_critical_poll = current_time
                
                # Poll all points at normal interval
                if (current_time - last_normal_poll) >= self.polling_config.normal_interval:
                    await self._poll_all_points()
                    last_normal_poll = current_time
                
                # Process pending writes
                await self._process_pending_writes()
                
                await asyncio.sleep(0.001)  # 1ms sleep
            
            except asyncio.CancelledError:
                logger.info("Polling loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(self.polling_config.normal_interval)
    
    async def _poll_critical_points(self) -> None:
        """Fast polling for critical points"""
        if not self.critical_points:
            return
        
        try:
            # Group critical points by backend
            backend_points: Dict[str, List[str]] = {}
            for point_name in self.critical_points:
                backend_name = self._get_backend_name_for_point(point_name)
                if backend_name:
                    if backend_name not in backend_points:
                        backend_points[backend_name] = []
                    backend_points[backend_name].append(point_name)
            
            # Read from each backend in parallel
            read_tasks = []
            for backend_name, points in backend_points.items():
                backend = self.backends.get(backend_name)
                if backend:
                    read_tasks.append(backend.read_all())
            
            results = await asyncio.gather(*read_tasks, return_exceptions=True)
            
            # Process results
            changes = []
            async with self._state_lock:
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    
                    for point_name, new_value in result.items():
                        if point_name in self.critical_points:
                            old_value = self.current_states.get(point_name)
                            if old_value != new_value:
                                self.current_states[point_name] = new_value
                                point = self.points.get(point_name)
                                if point:
                                    change = StateChange.create(
                                        point_name=point_name,
                                        old_value=old_value,
                                        new_value=new_value,
                                        hardware_ref=point.hardware_ref
                                    )
                                    changes.append(change)
            
            # Notify changes
            if changes:
                await self._notify_changes(changes)
        
        except Exception as e:
            logger.error(f"Error polling critical points: {e}")
    
    async def _poll_all_points(self) -> None:
        """Poll all I/O points"""
        try:
            # Read from all backends in parallel
            read_tasks = [backend.read_all() for backend in self.backends.values()]
            results = await asyncio.gather(*read_tasks, return_exceptions=True)
            
            # Process results
            changes = []
            async with self._state_lock:
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    
                    for point_name, new_value in result.items():
                        old_value = self.current_states.get(point_name)
                        if old_value != new_value:
                            self.current_states[point_name] = new_value
                            point = self.points.get(point_name)
                            if point:
                                change = StateChange.create(
                                    point_name=point_name,
                                    old_value=old_value,
                                    new_value=new_value,
                                    hardware_ref=point.hardware_ref
                                )
                                changes.append(change)
            
            # Notify changes
            if changes:
                await self._notify_changes(changes)
        
        except Exception as e:
            logger.error(f"Error polling all points: {e}")
    
    async def _process_pending_writes(self) -> None:
        """Process pending write operations"""
        if not self._pending_writes:
            return
        
        try:
            # Group writes by backend
            backend_writes: Dict[str, Dict[str, Any]] = {}
            async with self._batch_lock:
                for point_name, value in self._pending_writes.items():
                    backend_name = self._get_backend_name_for_point(point_name)
                    if backend_name:
                        if backend_name not in backend_writes:
                            backend_writes[backend_name] = {}
                        backend_writes[backend_name][point_name] = value
                self._pending_writes.clear()
            
            # Process writes for each backend
            write_tasks = []
            for backend_name, writes in backend_writes.items():
                backend = self.backends.get(backend_name)
                if backend:
                    for point_name, value in writes.items():
                        write_tasks.append(backend.write_point(point_name, value))
            
            # Wait for all writes to complete
            await asyncio.gather(*write_tasks)
        
        except Exception as e:
            logger.error(f"Error processing pending writes: {e}")
    
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
        if point.hardware_ref.startswith('sim'):
            return self.backends.get('simulator')
        elif point.hardware_ref.startswith('mcp'):
            return self.backends.get('mcp')
        return None
    
    def _get_backend_name_for_point(self, point_name: str) -> Optional[str]:
        """Get backend name for I/O point"""
        point = self.points.get(point_name)
        if not point:
            return None
        
        if point.hardware_ref.startswith('sim'):
            return 'simulator'
        elif point.hardware_ref.startswith('mcp'):
            return 'mcp'
        return None 