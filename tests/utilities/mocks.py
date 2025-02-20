"""
Mock objects for testing.
"""
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class MonitoringState:
    """State data for monitoring coordinator."""
    stream_health: bool = True
    recovery_attempts: int = 0
    buffer_size: int = 480
    cpu_usage: float = 0.0
    memory_usage: int = 0

class MockMonitoringCoordinator:
    """Mock monitoring coordinator for testing."""
    
    def __init__(self):
        self.logger = logging.getLogger("mock_coordinator")
        self._state = MonitoringState()
        self._is_monitoring = False
        self._shutdown_requested = False
        self._registered_threads = set()
        
    def start_monitoring(self):
        """Start monitoring simulation."""
        self._is_monitoring = True
        self.logger.info("Mock monitoring started")
        
    def stop_monitoring(self):
        """Stop monitoring simulation."""
        self._is_monitoring = False
        self.logger.info("Mock monitoring stopped")
        
    def request_shutdown(self):
        """Request shutdown of monitoring."""
        self._shutdown_requested = True
        self.logger.info("Shutdown requested")
        
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown was requested."""
        return self._shutdown_requested
        
    def register_thread(self):
        """Register a thread for monitoring."""
        thread_id = id(self)  # Use object id as mock thread id
        self._registered_threads.add(thread_id)
        self.logger.info(f"Thread {thread_id} registered")
        
    def unregister_thread(self):
        """Unregister a thread from monitoring."""
        thread_id = id(self)
        if thread_id in self._registered_threads:
            self._registered_threads.remove(thread_id)
            self.logger.info(f"Thread {thread_id} unregistered")
            
    def get_state(self) -> MonitoringState:
        """Get current monitoring state."""
        return self._state
        
    def update_state(self, **kwargs):
        """Update monitoring state."""
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)
                self.logger.info(f"State updated: {key}={value}")
            else:
                self.logger.warning(f"Unknown state attribute: {key}")
                
    def handle_error(self, error: Exception, component: str):
        """Handle component error."""
        self.logger.error(f"Error in {component}: {str(error)}")
        
    def mark_component_cleanup_complete(self, component: str):
        """Mark component cleanup as complete."""
        self.logger.info(f"Component cleanup complete: {component}")
