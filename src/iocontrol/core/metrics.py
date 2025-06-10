"""Performance metrics and monitoring for IoControl"""

from __future__ import annotations
import time
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque

@dataclass
class OperationMetrics:
    """Metrics for a single operation type"""
    count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    recent_times: deque = field(default_factory=lambda: deque(maxlen=100))
    error_count: int = 0
    
    @property
    def avg_time(self) -> float:
        """Calculate average operation time"""
        return self.total_time / self.count if self.count > 0 else 0.0
    
    def update(self, duration: float, error: bool = False) -> None:
        """Update metrics with a new operation"""
        self.count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.recent_times.append(duration)
        if error:
            self.error_count += 1

@dataclass
class BackendMetrics:
    """Metrics for a specific backend"""
    read: OperationMetrics = field(default_factory=OperationMetrics)
    write: OperationMetrics = field(default_factory=OperationMetrics)
    last_update: float = field(default_factory=time.time)
    
    def update_read(self, duration: float, error: bool = False) -> None:
        """Update read metrics"""
        self.read.update(duration, error)
        self.last_update = time.time()
    
    def update_write(self, duration: float, error: bool = False) -> None:
        """Update write metrics"""
        self.write.update(duration, error)
        self.last_update = time.time()

class PerformanceMonitor:
    """High-performance metrics monitoring"""
    
    def __init__(self):
        self.backends: Dict[str, BackendMetrics] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes
    
    async def record_operation(
        self,
        backend_name: str,
        operation: str,
        duration: float,
        error: bool = False
    ) -> None:
        """Record an operation's metrics"""
        async with self._lock:
            if backend_name not in self.backends:
                self.backends[backend_name] = BackendMetrics()
            
            metrics = self.backends[backend_name]
            if operation == 'read':
                metrics.update_read(duration, error)
            elif operation == 'write':
                metrics.update_write(duration, error)
            
            # Periodically clean up stale metrics
            current_time = time.time()
            if current_time - self._last_cleanup > self._cleanup_interval:
                await self._cleanup_stale_metrics()
                self._last_cleanup = current_time
    
    async def get_metrics(self, backend_name: Optional[str] = None) -> Dict:
        """Get metrics for a specific backend or all backends"""
        async with self._lock:
            if backend_name:
                if backend_name not in self.backends:
                    return {}
                return self._format_metrics(backend_name, self.backends[backend_name])
            
            return {
                name: self._format_metrics(name, metrics)
                for name, metrics in self.backends.items()
            }
    
    def _format_metrics(self, backend_name: str, metrics: BackendMetrics) -> Dict:
        """Format metrics for output"""
        return {
            'backend': backend_name,
            'last_update': metrics.last_update,
            'read': {
                'count': metrics.read.count,
                'avg_time': metrics.read.avg_time,
                'min_time': metrics.read.min_time,
                'max_time': metrics.read.max_time,
                'error_count': metrics.read.error_count,
                'recent_avg': sum(metrics.read.recent_times) / len(metrics.read.recent_times) if metrics.read.recent_times else 0.0
            },
            'write': {
                'count': metrics.write.count,
                'avg_time': metrics.write.avg_time,
                'min_time': metrics.write.min_time,
                'max_time': metrics.write.max_time,
                'error_count': metrics.write.error_count,
                'recent_avg': sum(metrics.write.recent_times) / len(metrics.write.recent_times) if metrics.write.recent_times else 0.0
            }
        }
    
    async def _cleanup_stale_metrics(self) -> None:
        """Remove metrics for backends that haven't been updated recently"""
        current_time = time.time()
        stale_timeout = 3600  # 1 hour
        
        to_remove = [
            name for name, metrics in self.backends.items()
            if current_time - metrics.last_update > stale_timeout
        ]
        
        for name in to_remove:
            del self.backends[name] 