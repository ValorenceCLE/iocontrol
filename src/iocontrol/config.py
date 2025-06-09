"""Runtime Configuration Management for IoControl"""

from __future__ import annotations
import asyncio
import logging
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import copy

from .types import IoPoint, IoType

logger = logging.getLogger(__name__)

@dataclass
class ConfigChange:
    """Represents a configuration change"""
    timestamp: datetime
    change_type: str  # 'add', 'remove', 'modify'
    point_name: str
    old_config: Optional[Dict[str, Any]] = None
    new_config: Optional[Dict[str, Any]] = None
    user: str = "system"

@dataclass
class ConfigSnapshot:
    """Snapshot of configuration at a point in time"""
    timestamp: datetime
    config: Dict[str, Any]
    version: int
    changes_since_last: List[ConfigChange] = field(default_factory=list)

class RuntimeConfigManager:
    """Manages runtime configuration changes and hot-reloading"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self.current_config: Dict[str, Any] = {}
        self.config_history: List[ConfigSnapshot] = []
        self.change_callbacks: List[Callable[[List[ConfigChange]], None]] = []
        self._version = 0
        self._file_watcher_task: Optional[asyncio.Task] = None
        self._last_file_mtime = 0.0
        
    async def load_config(self, config_path: Path) -> bool:
        """Load configuration from file"""
        try:
            self.config_path = config_path
            
            with open(config_path, 'r') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    new_config = yaml.safe_load(f)
                else:
                    new_config = json.load(f)
            
            # Create snapshot of current config before changing
            if self.current_config:
                self._create_snapshot([])
            
            self.current_config = new_config
            self._version += 1
            self._last_file_mtime = config_path.stat().st_mtime
            
            logger.info(f"Loaded configuration from {config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            return False
    
    async def save_config(self, config_path: Optional[Path] = None) -> bool:
        """Save current configuration to file"""
        try:
            path = config_path or self.config_path
            if not path:
                raise ValueError("No config path specified")
            
            with open(path, 'w') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    yaml.dump(self.current_config, f, default_flow_style=False)
                else:
                    json.dump(self.current_config, f, indent=2)
            
            self._last_file_mtime = path.stat().st_mtime
            logger.info(f"Saved configuration to {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False
    
    async def add_io_point(self, point_config: Dict[str, Any], user: str = "system") -> bool:
        """Add a new I/O point at runtime"""
        try:
            point_name = point_config['name']
            
            # Validate the point configuration
            if not self._validate_point_config(point_config):
                return False
            
            # Check if point already exists
            existing_points = {p['name']: p for p in self.current_config.get('io_points', [])}
            if point_name in existing_points:
                logger.warning(f"I/O point {point_name} already exists")
                return False
            
            # Add to configuration
            if 'io_points' not in self.current_config:
                self.current_config['io_points'] = []
            
            self.current_config['io_points'].append(point_config)
            
            # Track change
            change = ConfigChange(
                timestamp=datetime.now(),
                change_type='add',
                point_name=point_name,
                new_config=point_config,
                user=user
            )
            
            await self._notify_changes([change])
            self._version += 1
            
            logger.info(f"Added I/O point: {point_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add I/O point: {e}")
            return False
    
    async def remove_io_point(self, point_name: str, user: str = "system") -> bool:
        """Remove an I/O point at runtime"""
        try:
            io_points = self.current_config.get('io_points', [])
            
            # Find and remove the point
            for i, point in enumerate(io_points):
                if point['name'] == point_name:
                    old_config = io_points.pop(i)
                    
                    # Track change
                    change = ConfigChange(
                        timestamp=datetime.now(),
                        change_type='remove',
                        point_name=point_name,
                        old_config=old_config,
                        user=user
                    )
                    
                    await self._notify_changes([change])
                    self._version += 1
                    
                    logger.info(f"Removed I/O point: {point_name}")
                    return True
            
            logger.warning(f"I/O point {point_name} not found")
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove I/O point {point_name}: {e}")
            return False
    
    async def modify_io_point(self, point_name: str, new_config: Dict[str, Any], user: str = "system") -> bool:
        """Modify an existing I/O point configuration"""
        try:
            if not self._validate_point_config(new_config):
                return False
            
            io_points = self.current_config.get('io_points', [])
            
            # Find and modify the point
            for i, point in enumerate(io_points):
                if point['name'] == point_name:
                    old_config = copy.deepcopy(point)
                    io_points[i] = new_config
                    
                    # Track change
                    change = ConfigChange(
                        timestamp=datetime.now(),
                        change_type='modify',
                        point_name=point_name,
                        old_config=old_config,
                        new_config=new_config,
                        user=user
                    )
                    
                    await self._notify_changes([change])
                    self._version += 1
                    
                    logger.info(f"Modified I/O point: {point_name}")
                    return True
            
            logger.warning(f"I/O point {point_name} not found")
            return False
            
        except Exception as e:
            logger.error(f"Failed to modify I/O point {point_name}: {e}")
            return False
    
    async def start_file_watching(self) -> None:
        """Start watching config file for changes"""
        if not self.config_path or self._file_watcher_task:
            return
        
        self._file_watcher_task = asyncio.create_task(self._file_watcher_loop())
        logger.info(f"Started watching config file: {self.config_path}")
    
    async def stop_file_watching(self) -> None:
        """Stop watching config file"""
        if self._file_watcher_task:
            self._file_watcher_task.cancel()
            try:
                await self._file_watcher_task
            except asyncio.CancelledError:
                pass
            self._file_watcher_task = None
    
    def on_config_change(self, callback: Callable[[List[ConfigChange]], None]) -> None:
        """Register callback for configuration changes"""
        self.change_callbacks.append(callback)
    
    def get_config_history(self, limit: int = 10) -> List[ConfigSnapshot]:
        """Get configuration change history"""
        return self.config_history[-limit:]
    
    async def rollback_to_version(self, version: int) -> bool:
        """Rollback configuration to a previous version"""
        try:
            for snapshot in reversed(self.config_history):
                if snapshot.version == version:
                    old_config = copy.deepcopy(self.current_config)
                    self.current_config = copy.deepcopy(snapshot.config)
                    self._version += 1
                    
                    # Create rollback change record
                    change = ConfigChange(
                        timestamp=datetime.now(),
                        change_type='rollback',
                        point_name='system',
                        old_config={'version': self._version - 1, 'config': old_config},
                        new_config={'version': version, 'config': self.current_config},
                        user='system'
                    )
                    
                    await self._notify_changes([change])
                    logger.info(f"Rolled back configuration to version {version}")
                    return True
            
            logger.warning(f"Version {version} not found in history")
            return False
            
        except Exception as e:
            logger.error(f"Failed to rollback to version {version}: {e}")
            return False
    
    # Private methods
    
    def _validate_point_config(self, config: Dict[str, Any]) -> bool:
        """Validate I/O point configuration"""
        required_fields = ['name', 'io_type', 'hardware_ref']
        
        for field in required_fields:
            if field not in config:
                logger.error(f"Missing required field: {field}")
                return False
        
        # Validate io_type
        try:
            IoType(config['io_type'])
        except ValueError:
            logger.error(f"Invalid io_type: {config['io_type']}")
            return False
        
        return True
    
    def _create_snapshot(self, changes: List[ConfigChange]) -> None:
        """Create a configuration snapshot"""
        snapshot = ConfigSnapshot(
            timestamp=datetime.now(),
            config=copy.deepcopy(self.current_config),
            version=self._version,
            changes_since_last=changes
        )
        
        self.config_history.append(snapshot)
        
        # Keep only last 50 snapshots
        if len(self.config_history) > 50:
            self.config_history.pop(0)
    
    async def _notify_changes(self, changes: List[ConfigChange]) -> None:
        """Notify all callbacks about configuration changes"""
        self._create_snapshot(changes)
        
        for callback in self.change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(changes)
                else:
                    await asyncio.to_thread(callback, changes)
            except Exception as e:
                logger.error(f"Error in config change callback: {e}")
    
    async def _file_watcher_loop(self) -> None:
        """Watch config file for external changes"""
        while True:
            try:
                if self.config_path and self.config_path.exists():
                    current_mtime = self.config_path.stat().st_mtime
                    
                    if current_mtime > self._last_file_mtime:
                        logger.info("Config file changed externally, reloading...")
                        await self.load_config(self.config_path)
                        
                        # Notify about external change
                        change = ConfigChange(
                            timestamp=datetime.now(),
                            change_type='external_reload',
                            point_name='system',
                            user='external'
                        )
                        await self._notify_changes([change])
                
                await asyncio.sleep(1.0)  # Check every second
                
            except asyncio.CancelledError:
                logger.info("File watcher cancelled")
                break
            except Exception as e:
                logger.error(f"Error in file watcher: {e}")
                await asyncio.sleep(5.0)  # Wait before retrying