#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "AlertSystem",
    "type": "Core Component",
    "description": "System resource monitoring and alerting system with dynamic thresholds, alert management, and performance tracking",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                AS[AlertSystem] --> AC[AlertConfig]
                AS --> AH[AlertHistory]
                AS --> AL[Alert]
                AS --> MC[MonitoringCoordinator]
                AS --> QO[QObject]
                AC --> TH[ThresholdHistory]
                AH --> AL
                AS --> PM[PerformanceMetrics]
        ```",
        "dependencies": {
            "AlertConfig": "Alert threshold configuration",
            "AlertHistory": "Alert tracking and suppression",
            "Alert": "Alert data structure",
            "MonitoringCoordinator": "System monitoring",
            "QObject": "Qt signal handling",
            "ThresholdHistory": "Dynamic threshold adjustment",
            "PerformanceMetrics": "System performance tracking"
        }
    },
    "notes": [
        "Monitors CPU, memory, storage, and buffer usage",
        "Implements dynamic threshold adjustment",
        "Provides alert suppression and rate limiting",
        "Tracks performance metrics and alert history",
        "Ensures thread-safe operations",
        "Supports cleanup and resource management"
    ],
    "usage": {
        "examples": [
            "alert_system = AlertSystem(config, coordinator)",
            "await alert_system.monitor_resources()",
            "metrics = alert_system.get_performance_metrics()"
        ]
    },
    "requirements": {
        "python_version": "3.13 or later",
        "dependencies": [
            "asyncio",
            "psutil",
            "PySide6",
            "threading"
        ],
        "system": {
            "memory": "Sufficient for monitoring",
            "permissions": "Process monitoring access"
        }
    },
    "performance": {
        "execution_time": "Continuous monitoring with configurable intervals",
        "resource_usage": [
            "Light CPU usage for monitoring",
            "Minimal memory footprint",
            "Thread-safe operations",
            "Efficient alert suppression"
        ]
    }
}
"""
import asyncio
import logging
import psutil
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QObject, Signal

from .monitoring_coordinator import MonitoringCoordinator

logger = logging.getLogger(__name__)

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import tempfile

@dataclass
class Alert:
    """Represents a system alert with trigger status, message, and metadata."""
    triggered: bool
    message: str
    level: int = 1  # 1: Info, 2: Warning, 3: Critical
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    suppressed: bool = False

@dataclass
class AlertHistory:
    """Tracks alert history for aggregation and suppression."""
    alerts: list[Alert] = field(default_factory=list)
    max_size: int = 100
    
    def add(self, alert: Alert):
        """Add alert to history with size limit enforcement."""
        self.alerts.append(alert)
        if len(self.alerts) > self.max_size:
            self.alerts = self.alerts[-self.max_size:]
    
    def get_recent(self, minutes: int = 5) -> list[Alert]:
        """Get alerts from the last N minutes."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [a for a in self.alerts if a.timestamp > cutoff]
    
    def should_suppress(self, source: str, level: int) -> bool:
        """Check if similar alerts have been frequent."""
        recent = self.get_recent(minutes=1)
        similar = [a for a in recent if a.source == source and a.level == level]
        return len(similar) >= 3  # Suppress if 3+ similar alerts in last minute

class AlertConfig:
    """Configuration for system monitoring thresholds with dynamic adjustment."""
    def __init__(self, cpu_threshold: float = 80.0,
                 memory_threshold: float = 512.0,  # MB
                 storage_latency_threshold: float = 0.1,  # seconds
                 buffer_threshold: float = 90.0,
                 check_interval: float = 1.0,
                 alert_suppression: bool = True,
                 rate_limit_interval: float = 1.0,  # seconds
                 alert_history_size: int = 100,
                 dynamic_threshold_window: float = 60.0):  # seconds
        """Initialize alert configuration with smart defaults."""
        # Base thresholds
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.storage_latency_threshold = storage_latency_threshold
        self.buffer_threshold = buffer_threshold
        
        # Monitoring configuration
        self.check_interval = check_interval
        self.alert_suppression = alert_suppression
        self.rate_limit_interval = rate_limit_interval
        self.alert_history_size = alert_history_size
        
        # Dynamic threshold adjustments
        self.threshold_history = {
            'cpu': [],
            'memory': [],
            'latency': [],
            'buffer': []
        }
        self.adjustment_window = int(dynamic_threshold_window)  # Convert to samples
        self.validate()

    def validate(self):
        """Validate threshold values are within acceptable ranges."""
        if not (0 < self.cpu_threshold <= 100):
            raise ValueError("CPU threshold must be between 0 and 100")
        if not (self.memory_threshold > 0):
            raise ValueError("Memory threshold must be positive")
        if not (self.storage_latency_threshold > 0):
            raise ValueError("Storage latency threshold must be positive")
        if not (0 < self.buffer_threshold <= 100):
            raise ValueError("Buffer threshold must be between 0 and 100")
        if not (self.check_interval > 0):
            raise ValueError("Check interval must be positive")
            
    def update_threshold_history(self, metric: str, value: float):
        """Update metric history for dynamic threshold adjustment."""
        history = self.threshold_history[metric]
        history.append(value)
        if len(history) > self.adjustment_window:
            history.pop(0)
            
    def get_dynamic_threshold(self, metric: str) -> float:
        """Get dynamically adjusted threshold based on recent history."""
        history = self.threshold_history[metric]
        if not history:
            return getattr(self, f"{metric}_threshold")
            
        # Use statistical analysis for dynamic adjustment
        mean = sum(history) / len(history)
        std_dev = (sum((x - mean) ** 2 for x in history) / len(history)) ** 0.5
        
        if metric == 'cpu':
            return min(self.cpu_threshold, mean + 2 * std_dev)
        elif metric == 'memory':
            return min(self.memory_threshold, mean + 2 * std_dev)
        elif metric == 'latency':
            return min(self.storage_latency_threshold, mean + 2 * std_dev)
        elif metric == 'buffer':
            return min(self.buffer_threshold, mean + 2 * std_dev)
        return getattr(self, f"{metric}_threshold")


class AlertSystem(QObject):
    """System resource monitoring and alerting system."""

    # Signal for alerts
    alert_triggered = Signal(str, str, int)  # title, message, level

    def __init__(self, config: AlertConfig, coordinator: MonitoringCoordinator):
        """Initialize the alert system with configuration and required coordinator."""
        super().__init__()
        if not coordinator:
            raise ValueError("MonitoringCoordinator is required")
        
        self.config = config
        self.coordinator = coordinator
        
        # Lock hierarchy (state -> metrics -> perf -> component -> update)
        self._state_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._perf_lock = threading.Lock()
        self._component_lock = threading.Lock()
        self._update_lock = threading.Lock()
        
        # Thread tracking
        self._registered_threads = set()
        
        # Alert management
        self._alert_history = AlertHistory(max_size=self.config.alert_history_size)
        self._last_emit = {}  # Track last emission time per source
        
        logger.info("Alert system initialized with config: %s", config)
        self.register_thread()
            
    def get_resource_metrics(self) -> dict:
        """Get resource metrics through coordinator."""
        with self._metrics_lock:
            return self.coordinator.get_component_metrics('alert_system')
            
    def get_performance_metrics(self) -> dict:
        """Get performance metrics through coordinator."""
        with self._perf_lock:
            return self.coordinator.get_performance_metrics('alert_system')
            
    def get_alert_statistics(self) -> dict:
        """Get statistical analysis of alert history."""
        with self._metrics_lock:
            total_alerts = len(self._alert_history.alerts)
            if total_alerts == 0:
                return {'total_alerts': 0, 'triggered_ratio': 0.0}
            
            triggered_alerts = sum(1 for a in self._alert_history.alerts if a.triggered)
            return {
                'total_alerts': total_alerts,
                'triggered_alerts': triggered_alerts,
                'triggered_ratio': triggered_alerts / total_alerts,
                'suppressed_alerts': sum(1 for a in self._alert_history.alerts if a.suppressed)
            }
            
    def get_alert_history(self) -> list[Alert]:
        """Get the current alert history."""
        with self._state_lock:
            return self._alert_history.alerts.copy()
            
    def get_current_thresholds(self) -> dict:
        """Get current dynamic thresholds for all metrics."""
        return {
            'cpu': self.config.get_dynamic_threshold('cpu'),
            'memory': self.config.get_dynamic_threshold('memory'),
            'latency': self.config.get_dynamic_threshold('latency'),
            'buffer': self.config.get_dynamic_threshold('buffer')
        }
            
    async def _should_emit_alert(self, source: str, level: int) -> bool:
        """Check if alert should be emitted based on history and rate limiting."""
        async with self.coordinator.component_lock('alert_system'):
            if not self.config.alert_suppression:
                return True
                
            # Check suppression through coordinator
            if await self.coordinator.should_suppress_alert(source, level):
                logger.debug(f"Suppressing alert from {source} (level {level})")
                return False
                
            # Rate limiting with proper interval
            now = time.time()
            last_time = self._last_emit.get(source, 0)
            interval = self.config.rate_limit_interval
                
            if now - last_time < interval:
                logger.debug(f"Rate limiting alert from {source} (level {level})")
                return False
                
            self._last_emit[source] = now
            return True
        
    async def _emit_alert(self, title: str, message: str, level: int, source: str):
        """Thread-safe alert emission with suppression and metrics tracking."""
        try:
            should_emit = await self._should_emit_alert(source, level)
            alert = Alert(
                triggered=True,
                message=message,
                level=level,
                source=source,
                suppressed=not should_emit
            )
            
            async with self.coordinator.component_lock('alert_system'):
                self._alert_history.add(alert)
                
                if should_emit:
                    # Update metrics through coordinator
                    await self.coordinator.increment_metric('alert_system', 'alert_count')
                    self.alert_triggered.emit(title, message, level)
        except Exception as e:
            logger.error(f"Alert emission failed: {e}")
            # Report error through coordinator
            await self.coordinator.report_error('alert_system', str(e))

    async def register_thread(self):
        """Thread-safe thread registration with error handling."""
        thread = threading.current_thread()
        try:
            async with self.coordinator.component_lock('alert_system'):
                if thread not in self._registered_threads:
                    await self.coordinator.register_thread()
                    self._registered_threads.add(thread)
                    logger.debug(f"Registered thread: {thread.name}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Thread registration failed: {e}")
            await self.coordinator.report_error('alert_system', f"Thread registration failed: {e}")
            return False

    async def unregister_thread(self):
        """Thread-safe thread unregistration with error handling."""
        thread = threading.current_thread()
        try:
            async with self.coordinator.component_lock('alert_system'):
                if thread in self._registered_threads:
                    await self.coordinator.unregister_thread()
                    self._registered_threads.remove(thread)
                    logger.debug(f"Unregistered thread: {thread.name}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Thread unregistration failed: {e}")
            await self.coordinator.report_error('alert_system', f"Thread unregistration failed: {e}")
            return False

    async def cleanup(self):
        """Clean up resources and unregister from coordinator with proper locking."""
        try:
            # Follow lock hierarchy: state -> metrics -> perf -> component -> update
            async with self.coordinator.component_lock('alert_system'):
                # Unregister all threads
                threads = list(self._registered_threads)
                for thread in threads:
                    try:
                        if thread in self._registered_threads:
                            await self.coordinator.unregister_thread()
                            self._registered_threads.remove(thread)
                    except Exception as e:
                        error_msg = f"Error unregistering thread {thread.name}: {e}"
                        logger.error(error_msg)
                        await self.coordinator.report_error('alert_system', error_msg)
                
                # Clear alert history and report cleanup
                self._alert_history = AlertHistory(max_size=self.config.alert_history_size)
                self._last_emit.clear()
                
                # Report cleanup completion
                await self.coordinator.report_status('alert_system', 'cleanup_completed')
                logger.info("Alert system cleanup completed")
                
        except Exception as e:
            error_msg = f"Error during alert system cleanup: {e}"
            logger.error(error_msg)
            await self.coordinator.report_error('alert_system', error_msg)
            raise

    async def check_cpu_usage(self) -> Alert:
        """Monitor CPU usage with dynamic thresholds."""
        try:
            # Get CPU usage through coordinator
            cpu_percent = await self.coordinator.get_system_metric('cpu_usage')
            
            # Update threshold history and coordinator metrics
            self.config.update_threshold_history('cpu', cpu_percent)
            await self.coordinator.update_metric('alert_system', 'cpu_threshold', 
                                               self.config.get_dynamic_threshold('cpu'))
            
            threshold = self.config.get_dynamic_threshold('cpu')
            
            if cpu_percent > threshold:
                message = f"CPU usage ({cpu_percent:.1f}%) exceeds threshold ({threshold:.1f}%)"
                logger.warning(message)
                await self._emit_alert("CPU Alert", message, 2, "cpu")  # Critical level
                return Alert(triggered=True, message=message, level=2, source="cpu")
            
            # Update normal status through coordinator
            await self.coordinator.update_status('alert_system', 'cpu_normal')
            return Alert(triggered=False, message="CPU usage normal", source="cpu")
            
        except Exception as e:
            message = f"Failed to check CPU usage: {e}"
            logger.error(message)
            await self._emit_alert("CPU Error", message, 3, "cpu")  # Error level
            await self.coordinator.report_error('alert_system', f"CPU check failed: {e}")
            return Alert(triggered=True, message=message, level=3, source="cpu")

    async def check_memory_usage(self) -> Alert:
        """Monitor memory usage with dynamic thresholds."""
        try:
            # Get memory usage through coordinator
            memory_mb = await self.coordinator.get_system_metric('memory_usage')
            
            # Update threshold history and coordinator metrics
            self.config.update_threshold_history('memory', memory_mb)
            await self.coordinator.update_metric('alert_system', 'memory_threshold',
                                               self.config.get_dynamic_threshold('memory'))
            
            threshold = self.config.get_dynamic_threshold('memory')
            
            if memory_mb > threshold:
                message = f"Memory usage ({memory_mb:.1f}MB) exceeds threshold ({threshold:.1f}MB)"
                logger.warning(message)
                await self._emit_alert("Memory Alert", message, 2, "memory")  # Critical level
                return Alert(triggered=True, message=message, level=2, source="memory")
            
            # Update normal status through coordinator
            await self.coordinator.update_status('alert_system', 'memory_normal')
            return Alert(triggered=False, message="Memory usage normal", source="memory")
            
        except Exception as e:
            message = f"Failed to check memory usage: {e}"
            logger.error(message)
            await self._emit_alert("Memory Error", message, 3, "memory")  # Error level
            await self.coordinator.report_error('alert_system', f"Memory check failed: {e}")
            return Alert(triggered=True, message=message, level=3, source="memory")

    async def check_storage_latency(self) -> Alert:
        """Monitor storage write latency using coordinator."""
        try:
            # Get storage latency through coordinator
            latency = await self.coordinator.get_system_metric('storage_latency')
            
            # Update threshold history and coordinator metrics
            self.config.update_threshold_history('latency', latency)
            await self.coordinator.update_metric('alert_system', 'latency_threshold',
                                               self.config.get_dynamic_threshold('latency'))
            
            threshold = self.config.get_dynamic_threshold('latency')
            
            if latency > threshold:
                message = f"Storage latency ({latency:.3f}s) exceeds threshold ({threshold:.3f}s)"
                logger.warning(message)
                await self._emit_alert("Storage Alert", message, 1, "storage")  # Warning level
                return Alert(triggered=True, message=message, level=1, source="storage")
            
            # Update normal status through coordinator
            await self.coordinator.update_status('alert_system', 'storage_normal')
            return Alert(triggered=False, message="Storage latency normal", source="storage")
            
        except Exception as e:
            message = f"Failed to check storage latency: {e}"
            logger.error(message)
            await self._emit_alert("Storage Error", message, 3, "storage")  # Error level
            await self.coordinator.report_error('alert_system', f"Storage check failed: {e}")
            return Alert(triggered=True, message=message, level=3, source="storage")

    async def check_buffer_usage(self) -> Alert:
        """Monitor buffer usage with dynamic thresholds."""
        try:
            # Get buffer usage through coordinator
            buffer_usage = await self.coordinator.get_system_metric('buffer_usage')
            
            # Update threshold history and coordinator metrics
            self.config.update_threshold_history('buffer', buffer_usage)
            await self.coordinator.update_metric('alert_system', 'buffer_threshold',
                                               self.config.get_dynamic_threshold('buffer'))
            
            threshold = self.config.get_dynamic_threshold('buffer')
            
            if buffer_usage > threshold:
                message = f"Buffer usage ({buffer_usage:.1f}%) exceeds threshold ({threshold:.1f}%)"
                logger.warning(message)
                await self._emit_alert("Buffer Alert", message, 1, "buffer")  # Warning level
                return Alert(triggered=True, message=message, level=1, source="buffer")
            
            # Update normal status through coordinator
            await self.coordinator.update_status('alert_system', 'buffer_normal')
            return Alert(triggered=False, message="Buffer usage normal", source="buffer")
            
        except Exception as e:
            message = f"Failed to check buffer usage: {e}"
            logger.error(message)
            await self._emit_alert("Buffer Error", message, 3, "buffer")  # Error level
            await self.coordinator.report_error('alert_system', f"Buffer check failed: {e}")
            return Alert(triggered=True, message=message, level=3, source="buffer")

    async def monitor_resources(self):
        """Continuously monitor all system resources with dynamic intervals."""
        try:
            # Register monitoring task with coordinator
            await self.coordinator.register_monitoring_task('alert_system')
            
            while True:
                try:
                    # Update monitoring status
                    await self.coordinator.update_status('alert_system', 'monitoring_active')
                    
                    alerts = await asyncio.gather(
                        self.check_cpu_usage(),
                        self.check_memory_usage(),
                        self.check_storage_latency(),
                        self.check_buffer_usage(),
                        return_exceptions=True
                    )
                    
                    # Process any alerts that were triggered
                    for alert in alerts:
                        if isinstance(alert, Exception):
                            logger.error("Error during resource monitoring: %s", alert)
                            await self._emit_alert("Monitoring Error", str(alert), 3, "monitor")
                            await self.coordinator.report_error('alert_system', f"Monitoring error: {alert}")
                        elif alert.triggered and not alert.suppressed:
                            logger.warning(alert.message)
                            # Update monitoring metrics
                            await self.coordinator.increment_metric('alert_system', 'triggered_alerts')
                    
                    # Update monitoring metrics
                    await self.coordinator.update_metric('alert_system', 'last_check_time', time.time())
                    
                    # Dynamic sleep interval based on alert history and coordinator state
                    if self._alert_history.get_recent(minutes=1) or await self.coordinator.is_system_stressed():
                        # More frequent checks if recent alerts or system stress
                        await asyncio.sleep(self.config.check_interval / 2)
                    else:
                        await asyncio.sleep(self.config.check_interval)
                        
                except Exception as e:
                    error_msg = f"Error in resource monitoring loop: {e}"
                    logger.error(error_msg)
                    await self._emit_alert("Monitoring Error", error_msg, 3, "monitor")
                    await self.coordinator.report_error('alert_system', error_msg)
                    await asyncio.sleep(5)  # Back off on error
                    
        except Exception as e:
            error_msg = f"Fatal error in monitoring task: {e}"
            logger.error(error_msg)
            await self.coordinator.report_error('alert_system', error_msg)
            raise
        finally:
            # Ensure monitoring task is unregistered
            try:
                await self.coordinator.unregister_monitoring_task('alert_system')
            except Exception as e:
                logger.error(f"Error unregistering monitoring task: {e}")
