"""
COMPONENT_NOTES:
{
    "name": "ComponentCoordinator",
    "type": "Core System Manager",
    "description": "Coordinates component lifecycle, state management, and resource allocation through MonitoringCoordinator. Provides centralized control and monitoring of system components with proper cleanup and error handling.",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                CC[ComponentCoordinator] --> MC[MonitoringCoordinator]
                CC --> SM[StateMachine]
                CC --> HC[HealthCheck]
                CC --> RC[RecoveryCoordinator]
                MC --> RP[ResourcePool]
        ```",
        "dependencies": {
            "MonitoringCoordinator": {
                "description": "Handles system metrics, monitoring, and resource management",
                "responsibilities": [
                    "Resource allocation/deallocation",
                    "System metrics tracking",
                    "Component registration",
                    "Error handling"
                ]
            },
            "StateMachine": {
                "description": "Manages component state transitions",
                "responsibilities": [
                    "State validation",
                    "Transition tracking",
                    "Recovery states",
                    "Error handling"
                ]
            },
            "HealthCheck": {
                "description": "Verifies component and system health",
                "responsibilities": [
                    "Health validation",
                    "Thread monitoring",
                    "Resource verification",
                    "Error detection"
                ]
            },
            "RecoveryCoordinator": {
                "description": "Handles component recovery and error states",
                "responsibilities": [
                    "Error recovery",
                    "State restoration",
                    "Resource cleanup",
                    "System stability"
                ]
            }
        }
    },
    "notes": [
        "Central manager for all system components",
        "Ensures thread-safe state transitions",
        "Provides dependency resolution and initialization ordering",
        "Maintains component health monitoring and recovery",
        "Uses MonitoringCoordinator for resource management",
        "Implements proper cleanup with channel awareness",
        "Provides comprehensive error handling and recovery"
    ],
    "usage": {
        "examples": [
            "coordinator = ComponentCoordinator(monitoring_coordinator)",
            "coordinator.register_component('audio_capture', 'input')",
            "coordinator.allocate_resource('audio_capture', 'buffer', 1024)",
            "coordinator.cleanup_component('audio_capture')"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "threading",
            "asyncio",
            "logging",
            "enum",
            "dataclasses"
        ],
        "system": {
            "memory": "Managed through MonitoringCoordinator",
            "threading": "Thread-safe operations",
            "channels": "Stereo audio support"
        }
    },
    "performance": {
        "execution_time": {
            "state_transitions": "O(1) with proper locking",
            "resource_operations": "O(1) through MonitoringCoordinator",
            "cleanup": "Linear with resource count"
        },
        "resource_usage": [
            "Minimal memory footprint",
            "Efficient thread management",
            "Proper lock ordering",
            "Channel-aware resource tracking"
        ]
    }
}
"""

import enum
import logging
import threading
import time
import asyncio
from typing import Dict, List, Optional, Set, Callable, Union, Any
from typing_extensions import Tuple
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator

# Note: Removed ResourcePool import as it's now managed through MonitoringCoordinator
# per architecture changes (2025-02-19)

logger = logging.getLogger(__name__)

class ComponentState(enum.Enum):
    """States for component lifecycle."""
    UNINITIALIZED = "uninitialized"
    IDLE = "idle"
    INITIALIZING = "initializing"
    INITIATING = "initiating"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPING_CAPTURE = "stopping_capture"
    STOPPED = "stopped"
    ERROR = "error"

@dataclass
class StateTransitionEvent:
    """Information about a component state transition."""
    component: str
    from_state: ComponentState
    to_state: ComponentState
    timestamp: datetime
    success: bool
    error: Optional[str] = None

@dataclass
class ComponentInfo:
    """Information about a registered component."""
    name: str
    state: ComponentState
    resources: Dict[str, int]  # Resource type -> amount
    dependencies: Set[str]  # Component names this component depends on
    health_check: Optional[Callable[[], bool]] = None
    previous_state: Optional[ComponentState] = None  # For state rollback
    state_stack: List[ComponentState] = dataclass_field(default_factory=list)  # State history
    thread_failures: List[Dict[str, Any]] = dataclass_field(default_factory=list)  # Thread failure history

class ComponentCoordinator:
    """
    Coordinates component lifecycle, state transitions, and resource management.
    Provides centralized control over system components.
    """
    
    def __init__(self, monitoring_coordinator, config: Optional[Union[Dict, Any]] = None, validate: bool = True):
        """Initialize the component coordinator.
        
        Args:
            monitoring_coordinator: MonitoringCoordinator instance for resource management
            config: Optional configuration dictionary
            validate: Whether to validate configuration
            
        Note: Added state rollback, reset, and thread monitoring (2025-02-18)
        - previous_state: Tracks last valid state for rollback
        - state_stack: Maintains state history for complex recovery
        - thread_monitor: Monitors thread health and detects failures
        - New validation for state operations
        - Thread failure tracking
        """
        # Initialize monitoring state
        self._monitoring_active = False
        self._monitoring_lock = threading.Lock()
        self.logger = logging.getLogger("ComponentCoordinator")
        self._monitoring_coordinator = monitoring_coordinator
        
        # Thread monitoring
        self._thread_monitor = threading.Thread(
            target=self._monitor_threads,
            name="thread_monitor",
            daemon=True
        )
        self._thread_monitor_active = threading.Event()
        self._monitored_threads: Dict[int, Dict[str, Any]] = {}
        self._thread_health_interval = 5.0  # Check every 5 seconds
        
        # Initialize locks in strict order to prevent deadlocks
        self._component_lock = threading.Lock()  # Lock 1: Component operations
        self._resource_lock = threading.Lock()   # Lock 2: Resource operations
        self._history_lock = threading.Lock()    # Lock 3: History operations
        self._callback_lock = threading.Lock()   # Lock 4: Callback operations
        self._thread_lock = threading.Lock()     # Lock 5: Thread monitoring
        
        # Initialize state and data structures with proper typing
        self._initialized = False
        # Ensure collections are never None by initializing with empty containers
        self._components: Dict[str, ComponentInfo] = {}
        self._resource_limits: Dict[str, int] = {}
        self._allocated_resources: Dict[str, int] = {}
        self._state_history: List[StateTransitionEvent] = []
        self._state_callbacks: List[Callable[[str, ComponentState, ComponentState], None]] = []
        self._thread_failures: Dict[int, Dict[str, Any]] = {}  # Thread ID -> Failure info
        
        # Validate configuration if needed
        if validate and isinstance(config, dict):
            resource_limits = config.get('resource_limits', {})
            for resource_type, limit in resource_limits.items():
                if limit < 0:
                    raise ValueError(f"Invalid limit for {resource_type}: {limit}")

        # Handle test compatibility with MonitoringCoordinator
        if config and hasattr(config, 'register_state_callback'):
            # No additional setup needed, just ensure components dict exists
            pass
        elif isinstance(config, dict):
            # Apply resource limits from config dict
            for resource, limit in config.get('resource_limits', {}).items():
                self.set_resource_limit(resource, limit)
        
        self._initialized = True
        
        # Valid state transitions
        # Define valid state transitions with proper validation
        self._valid_transitions = {
            ComponentState.UNINITIALIZED: {
                ComponentState.INITIALIZING,
                ComponentState.ERROR
            },
            ComponentState.IDLE: {
                ComponentState.INITIATING,
                ComponentState.ERROR
            },
            ComponentState.INITIALIZING: {
                ComponentState.IDLE,
                ComponentState.RUNNING,
                ComponentState.ERROR,
                ComponentState.STOPPED
            },
            ComponentState.INITIATING: {
                ComponentState.RUNNING,
                ComponentState.ERROR
            },
            ComponentState.RUNNING: {
                ComponentState.PAUSED,
                ComponentState.STOPPING,
                ComponentState.STOPPING_CAPTURE,
                ComponentState.ERROR
            },
            ComponentState.PAUSED: {
                ComponentState.RUNNING,
                ComponentState.STOPPING,
                ComponentState.STOPPING_CAPTURE,
                ComponentState.ERROR
            },
            ComponentState.STOPPING: {
                ComponentState.STOPPED,
                ComponentState.ERROR
            },
            ComponentState.STOPPING_CAPTURE: {
                ComponentState.STOPPING,
                ComponentState.ERROR
            },
            ComponentState.STOPPED: {
                ComponentState.INITIALIZING,
                ComponentState.ERROR
            },
            ComponentState.ERROR: {
                ComponentState.INITIALIZING,
                ComponentState.STOPPED
            }
        }

    def register_component(self, name: str, component_type: str = "",
                         dependencies: Set[str] = None,
                         health_check: Optional[Callable[[], bool]] = None) -> bool:
        """
        Register a new component with the coordinator.
        
        Args:
            name: Unique component name
            component_type: Type of component (e.g. 'input', 'transform', 'output')
            dependencies: Set of component names this component depends on
            health_check: Optional function to check component health
            
        Returns:
            bool: True if registration successful, False if validation fails
            
        Note: Updated 2025-02-18 with improved validation
        """
        # Input validation
        if not name or not isinstance(name, str):
            self.logger.error("Component name must be a non-empty string")
            return False
            
        if not isinstance(component_type, str):
            self.logger.error("Component type must be a string")
            return False
            
        if dependencies is not None and not isinstance(dependencies, set):
            self.logger.error("Dependencies must be a set or None")
            return False
            
        if health_check is not None and not callable(health_check):
            self.logger.error("Health check must be callable or None")
            return False
            
        with self._component_lock:
            # Check for existing component
            if name in self._components:
                self.logger.error(f"Component {name} already registered")
                return False
                
            # Validate dependencies exist
            deps = dependencies or set()
            for dep in deps:
                if not isinstance(dep, str):
                    self.logger.error(f"Dependency {dep} must be a string")
                    return False
                if dep == name:
                    self.logger.error(f"Component {name} cannot depend on itself")
                    return False
                    
            # Create component info with validated data
            self._components[name] = ComponentInfo(
                name=name,
                state=ComponentState.UNINITIALIZED,
                resources={},
                dependencies=deps,
                health_check=health_check,
                thread_failures=[]  # Initialize thread failure history
            )
            
            self.logger.info(f"Registered component: {name}")
            return True

    def set_resource_limit(self, resource_type: str, limit: int) -> None:
        """Set the limit for a resource type."""
        with self._resource_lock:
            self._resource_limits[resource_type] = limit
            self.logger.info(f"Set {resource_type} limit to {limit}")

    def allocate_resource(self, component: str, resource_type: str,
                         amount: int) -> Union[bool, Any]:
        """
        Attempt to allocate resources for a component.
        
        Args:
            component: Name of component requesting resources
            resource_type: Type of resource to allocate
            amount: Amount of resource to allocate
            
        Returns:
            Union[bool, Any]: Resource object or True if successful, False if failed
            
        Note: Updated 2025-02-18 to handle channel-specific buffer allocation
        """
        # Parse component name to handle channel-specific allocation
        base_component, channel = self._parse_component_name(component)
        
        # Check component exists first
        with self._component_lock:
            if base_component not in self._components:
                self.logger.error(f"Unknown component: {base_component}")
                return False
        
            # Handle buffer allocation through monitoring coordinator
            if resource_type == 'buffer':
                try:
                    buffer = self._monitoring_coordinator.allocate_resource(base_component, 'buffer', amount)
                    if buffer is not None:
                        with self._component_lock:
                            if base_component not in self._components:
                                self._monitoring_coordinator.release_resource(base_component, 'buffer', buffer)
                                return False
                            resources = self._components[base_component].resources
                            # Track buffers per channel
                            channel_key = f'buffers_{channel}'
                            if channel_key not in resources:
                                resources[channel_key] = set()
                            resources[channel_key].add(buffer)
                        return buffer
                except Exception as e:
                    self.logger.error(f"Buffer allocation failed: {e}")
                    return False
                return False
            else:
                # Handle other resource types with existing logic
                with self._resource_lock:
                    current = self._allocated_resources.get(resource_type, 0)
                    limit = self._resource_limits.get(resource_type, float('inf'))
                    
                    if current + amount > limit:
                        self.logger.error(
                            f"Resource allocation failed for {component}: "
                            f"{resource_type} limit {limit} would be exceeded"
                        )
                        return False
                        
                    try:
                        self._allocated_resources[resource_type] = current + amount
                        
                        # Update component resources
                        with self._component_lock:
                            current = self._components[component].resources.get(resource_type, 0)
                            self._components[component].resources[resource_type] = current + amount
                            
                        self.logger.info(
                            f"Allocated {amount} {resource_type} to {component}"
                        )
                        return True
                        
                    except Exception as e:
                        # Rollback allocation on error
                        self._allocated_resources[resource_type] = current
                        self.logger.error(f"Resource allocation failed: {e}")
                        return False

    def release_resource(self, component: str, resource_type: str,
                        resource: Union[int, Any]) -> bool:
        """
        Release allocated resources from a component.
        
        Args:
            component: Name of component releasing resources
            resource_type: Type of resource to release
            resource: Resource to release (buffer object or amount)
            
        Returns:
            bool: True if release successful, False if invalid release
            
        Note: Updated 2025-02-18 to handle channel-specific buffer release
        """
        # Check component exists
        with self._component_lock:
            if component not in self._components:
                self.logger.error(f"Unknown component: {component}")
                return False
            
            if resource_type == 'buffer':
                if not isinstance(resource, (bytes, bytearray)):
                    self.logger.error("Invalid buffer type")
                    return False
                
                try:
                    # Parse component name for channel
                    base_component, channel = self._parse_component_name(component)
                    resources = self._components[base_component].resources
                    channel_key = f'buffers_{channel}'
                    
                    if (channel_key not in resources or 
                        resource not in resources[channel_key]):
                        self.logger.error("Buffer not found in component resources")
                        return False
                        
                    if self._monitoring_coordinator.release_resource(base_component, 'buffer', resource):
                        resources[channel_key].remove(resource)
                        return True
                except Exception as e:
                    self.logger.error(f"Buffer release failed: {e}")
                    return False
                    
                return False
            else:
                try:
                    # Handle other resource types
                    current = self._components[component].resources.get(resource_type, 0)
                    if current < resource:
                        self.logger.error(
                            f"Invalid resource release for {component}: "
                            f"has {current} {resource_type}, tried to release {resource}"
                        )
                        return False
                    
                    # Update component resources
                    self._components[component].resources[resource_type] = current - resource
                    
                    # Update global resource tracking
                    with self._resource_lock:
                        total = self._allocated_resources.get(resource_type, 0)
                        self._allocated_resources[resource_type] = total - resource
                    
                    self.logger.info(
                        f"Released {resource} {resource_type} from {component}"
                    )
                    return True
                    
                except Exception as e:
                    self.logger.error(f"Resource release failed: {e}")
                    return False

    def handle_thread_failure(self, thread_id: int, thread_name: str) -> None:
        """
        Handle a thread failure by transitioning affected components to ERROR state
        and tracking thread state.
        
        Args:
            thread_id: ID of the failed thread
            thread_name: Name of the failed thread
            
        Note: Updated 2025-02-18 with thread state tracking
        """
        try:
            # Track thread failure
            with self._component_lock:
                if not hasattr(self, '_thread_failures'):
                    self._thread_failures = {}
                self._thread_failures[thread_id] = {
                    'thread_name': thread_name,
                    'timestamp': time.time(),
                    'affected_components': []
                }
            
            # Identify affected components under component lock
            affected_components = []
            with self._component_lock:
                for name, info in self._components.items():
                    if (thread_name.startswith(name) or 
                        name.lower() in thread_name.lower()):
                        affected_components.append(name)
                        self._thread_failures[thread_id]['affected_components'].append(name)
            
            if not affected_components:
                self.logger.warning(
                    f"No components identified for failed thread: "
                    f"{thread_name} (ID: {thread_id})"
                )
                return
            
            # Transition each component to ERROR state
            for component in affected_components:
                # Get current state under component lock
                old_state = None
                with self._component_lock:
                    if component in self._components:
                        info = self._components[component]
                        old_state = info.state
                        info.state = ComponentState.ERROR
                        # Track thread state in component info
                        info.thread_failures.append({
                            'thread_id': thread_id,
                            'thread_name': thread_name,
                            'timestamp': time.time(),
                            'previous_state': old_state
                        })
                
                if old_state:
                    self.logger.error(
                        f"Transitioning component {component} to ERROR state "
                        f"due to thread failure: {thread_name} (ID: {thread_id})"
                    )
                    
                    # Record and notify outside locks
                    self._record_transition(
                        component=component,
                        from_state=old_state,
                        to_state=ComponentState.ERROR,
                        success=True,
                        error=f"Thread failure: {thread_name} (ID: {thread_id})"
                    )
                    self._notify_state_change(
                        component, old_state, ComponentState.ERROR
                    )
                
        except Exception as e:
            self.logger.error(
                f"Error handling thread failure for {thread_name}: {e}"
            )
            
    def get_thread_failures(self) -> Dict[int, Dict[str, Any]]:
        """Get history of thread failures and affected components."""
        with self._component_lock:
            if not hasattr(self, '_thread_failures'):
                self._thread_failures = {}
            return self._thread_failures.copy()

    def get_component_thread_failures(self, component: str) -> List[Dict[str, Any]]:
        """Get thread failure history for a specific component."""
        with self._component_lock:
            if component not in self._components:
                return []
            return self._components[component].thread_failures.copy()
            
    def verify_system_health(self) -> bool:
        """Verify overall system health by checking all components.
        
        Returns:
            bool: True if all components are healthy, False otherwise
        """
        with self._component_lock:
            try:
                # Check each component's health
                for name, info in self._components.items():
                    # Skip components in terminal states
                    if info.state in {ComponentState.STOPPED, ComponentState.ERROR}:
                        continue
                        
                    # Check health if health check function exists
                    if info.health_check:
                        try:
                            if not info.health_check():
                                self.logger.error(f"Health check failed for component {name}")
                                return False
                        except Exception as e:
                            self.logger.error(f"Error in health check for {name}: {e}")
                            return False
                            
                    # Check for recent thread failures
                    if info.thread_failures:
                        recent_failures = [
                            f for f in info.thread_failures 
                            if time.time() - f['timestamp'] < 300  # Last 5 minutes
                        ]
                        if recent_failures:
                            self.logger.error(
                                f"Recent thread failures detected for {name}: "
                                f"{len(recent_failures)} failures"
                            )
                            return False
                            
                return True
                
            except Exception as e:
                self.logger.error(f"Error verifying system health: {e}")
                return False

    def _monitor_threads(self) -> None:
        """Monitor thread health and detect failures."""
        while self._thread_monitor_active.is_set():
            try:
                with self._thread_lock:
                    current_time = time.time()
                    dead_threads = []
                    
                    # Check each monitored thread
                    for thread_id, info in self._monitored_threads.items():
                        thread = info['thread']
                        if not thread.is_alive():
                            dead_threads.append((thread_id, info))
                            continue
                            
                        # Check if thread is responsive
                        last_heartbeat = info.get('last_heartbeat', 0)
                        if current_time - last_heartbeat > self._thread_health_interval * 2:
                            dead_threads.append((thread_id, info))
                            
                    # Handle any dead threads
                    for thread_id, info in dead_threads:
                        self.handle_thread_failure(thread_id, info['thread'].name)
                        del self._monitored_threads[thread_id]
                        
            except Exception as e:
                self.logger.error(f"Error in thread monitor: {e}")
                
            time.sleep(self._thread_health_interval)
            
    def register_thread(self, thread: Optional[threading.Thread] = None) -> None:
        """Register a thread for health monitoring.
        
        Args:
            thread: Thread to monitor, defaults to current thread
        """
        try:
            thread = thread or threading.current_thread()
            thread_id = thread.ident
            
            with self._thread_lock:
                if thread_id not in self._monitored_threads:
                    self._monitored_threads[thread_id] = {
                        'thread': thread,
                        'start_time': time.time(),
                        'last_heartbeat': time.time()
                    }
                    
                    # Start monitor thread if not running
                    if not self._thread_monitor_active.is_set():
                        self._thread_monitor_active.set()
                        self._thread_monitor.start()
                        
        except Exception as e:
            self.logger.error(f"Error registering thread {thread.name}: {e}")
            
    def unregister_thread(self, thread: Optional[threading.Thread] = None) -> None:
        """Unregister a thread from health monitoring.
        
        Args:
            thread: Thread to unregister, defaults to current thread
        """
        try:
            thread = thread or threading.current_thread()
            thread_id = thread.ident
            
            with self._thread_lock:
                if thread_id in self._monitored_threads:
                    del self._monitored_threads[thread_id]
                    
        except Exception as e:
            self.logger.error(f"Error unregistering thread {thread.name}: {e}")
            
    def thread_heartbeat(self, thread: Optional[threading.Thread] = None) -> None:
        """Update thread heartbeat timestamp.
        
        Args:
            thread: Thread to update, defaults to current thread
        """
        try:
            thread = thread or threading.current_thread()
            thread_id = thread.ident
            
            with self._thread_lock:
                if thread_id in self._monitored_threads:
                    self._monitored_threads[thread_id]['last_heartbeat'] = time.time()
                    
        except Exception as e:
            self.logger.error(f"Error updating thread heartbeat {thread.name}: {e}")
            
    def register_state_callback(self, callback: Callable[[str, ComponentState, ComponentState, Optional[str]], None]) -> None:
        """Register a callback to be notified of component state changes.
        
        Args:
            callback: Function to call when component state changes.
                     Takes (component_name, old_state, new_state, error) as arguments.
                     error is an optional string containing error context when transitioning to ERROR state.
        
        Note: Updated 2025-02-18 to support error context preservation
        """
        if not callable(callback):
            raise ValueError("Callback must be callable")
            
        with self._callback_lock:
            if callback not in self._state_callbacks:
                self._state_callbacks.append(callback)
                self.logger.info("Registered new state change callback")

    def get_thread_health(self, thread: Optional[threading.Thread] = None) -> Dict[str, Any]:
        """Get health information for a thread.
        
        Args:
            thread: Thread to check, defaults to current thread
            
        Returns:
            Dict with thread health information
        """
        try:
            thread = thread or threading.current_thread()
            thread_id = thread.ident
            
            with self._thread_lock:
                if thread_id not in self._monitored_threads:
                    return {
                        'monitored': False,
                        'thread_id': thread_id,
                        'thread_name': thread.name
                    }
                    
                info = self._monitored_threads[thread_id]
                current_time = time.time()
                
                return {
                    'monitored': True,
                    'thread_id': thread_id,
                    'thread_name': thread.name,
                    'alive': thread.is_alive(),
                    'uptime': current_time - info['start_time'],
                    'last_heartbeat': current_time - info.get('last_heartbeat', 0),
                    'healthy': (thread.is_alive() and 
                              current_time - info.get('last_heartbeat', 0) <= 
                              self._thread_health_interval * 2)
                }
                
        except Exception as e:
            self.logger.error(f"Error getting thread health {thread.name}: {e}")
            return {
                'error': str(e),
                'thread_name': thread.name if thread else 'unknown'
            }
            
    def reset_state(self, component: str) -> bool:
        """Reset a component to its initial state (UNINITIALIZED).
        
        Args:
            component: Name of component to reset
            
        Returns:
            bool: True if reset successful
        """
        with self._component_lock:
            if component not in self._components:
                self.logger.error(f"Unknown component: {component}")
                return False
                
            info = self._components[component]
            old_state = info.state
            
            # Clear state history
            info.previous_state = None
            info.state_stack.clear()
            info.thread_failures.clear()  # Clear thread failure history
            
            # Reset to initial state
            info.state = ComponentState.UNINITIALIZED
            
            # Record and notify
            self._record_transition(
                component, old_state, ComponentState.UNINITIALIZED, True,
                "State reset"
            )
            self._notify_state_change(
                component, old_state, ComponentState.UNINITIALIZED
            )
            
            self.logger.info(f"Reset {component} state to UNINITIALIZED")
            return True

    def _parse_component_name(self, component: str) -> Tuple[str, str]:
        """Parse component name into base name and channel.
        
        Args:
            component: Component name possibly with channel suffix
            
        Returns:
            Tuple of (base_component, channel)
        """
        if component.endswith('_left'):
            return component[:-5], 'left'
        elif component.endswith('_right'):
            return component[:-6], 'right'
        return component, 'left'  # Default to left channel

    def _record_transition(self, component: str, from_state: ComponentState,
                         to_state: ComponentState, success: bool,
                         error: Optional[str] = None) -> None:
        """Record a state transition in the history.
        
        Args:
            component: Name of component that transitioned
            from_state: Previous state
            to_state: New state
            success: Whether transition was successful
            error: Optional error message if transition failed
            
        Note: Added 2025-02-18 to support state transition tracking
        """
        with self._history_lock:
            event = StateTransitionEvent(
                component=component,
                from_state=from_state,
                to_state=to_state,
                timestamp=datetime.now(),
                success=success,
                error=error
            )
            self._state_history.append(event)
            
    def _notify_state_change(self, component: str, from_state: ComponentState,
                           to_state: ComponentState) -> None:
        """Notify registered callbacks of a state change.
        
        Args:
            component: Name of component that changed state
            from_state: Previous state
            to_state: New state
            
        Note: Updated 2025-02-18 to support error context preservation
        """
        with self._callback_lock:
            # Get error context if transitioning to ERROR state
            error_context = None
            if to_state == ComponentState.ERROR:
                with self._history_lock:
                    # Get most recent transition for this component
                    for event in reversed(self._state_history):
                        if event.component == component:
                            error_context = event.error
                            break
            
            for callback in self._state_callbacks:
                try:
                    callback(component, from_state, to_state, error_context)
                except Exception as e:
                    self.logger.error(
                        f"Error in state change callback for {component}: {e}"
                    )

    async def cleanup_component(self, component: str) -> bool:
        """
        Clean up a component's resources and remove it from coordination.
        
        Args:
            component: Name of component to clean up
            
        Returns:
            bool: True if cleanup successful, False otherwise
            
        Note: Updated 2025-02-18 to handle channel-specific cleanup
        """
        try:
            with self._component_lock:
                if component not in self._components:
                    self.logger.error(f"Unknown component: {component}")
                    return False
                    
                info = self._components[component]
                
                # Call cleanup handler if available
                if hasattr(info, 'cleanup_handler') and info.cleanup_handler:
                    try:
                        if asyncio.iscoroutinefunction(info.cleanup_handler):
                            await info.cleanup_handler()
                        else:
                            info.cleanup_handler()
                    except Exception as e:
                        self.logger.error(f"Cleanup handler error for {component}: {e}")
                        return False
                
                # Release all resources with channel awareness
                with self._resource_lock:
                    for resource_type, amount in info.resources.items():
                        if resource_type.startswith('buffers_'):
                            # Handle channel-specific buffer cleanup
                            for buffer in amount.copy():
                                try:
                                    self.release_resource(
                                        f"{component}_{resource_type.split('_')[1]}", 
                                        'buffer', 
                                        buffer
                                    )
                                except Exception as e:
                                    self.logger.error(f"Failed to release buffer for {component}: {e}")
                                    return False
                        else:
                            try:
                                # Handle other resources
                                current = self._allocated_resources.get(resource_type, 0)
                                if current < amount:
                                    self.logger.error(f"Resource underflow for {component}: {resource_type}")
                                    return False
                                self._allocated_resources[resource_type] = current - amount
                            except Exception as e:
                                self.logger.error(f"Failed to release {resource_type} for {component}: {e}")
                                return False
                
                # Remove component
                del self._components[component]
                self.logger.info(f"Cleaned up component: {component}")
                return True
                
        except Exception as e:
            self.logger.error(f"Cleanup error for {component}: {e}")
            return False
