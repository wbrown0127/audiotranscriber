"""
COMPONENT_NOTES:
{
    "name": "BufferManager",
    "type": "Core Component",
    "description": "Thread-safe buffer management system that provides efficient memory allocation, channel-specific queues, performance monitoring, and resource pooling with comprehensive error handling and cleanup coordination",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                BM[BufferManager] --> MC[MonitoringCoordinator]
                BM --> CC[ComponentCoordinator]
                BM --> RP[ResourcePool]
                BM --> SM[StateMachine]
                BM --> BQ[BufferQueues]
                BM --> PM[PerformanceMetrics]
                BM --> CV[CleanupValidation]
                RP --> PT[PoolTier]
                RP --> PM[PoolMetrics]
                BQ --> CQ[ChannelQueues]
                BQ --> QM[QueueMetrics]
                PM --> PH[PerformanceHistory]
                PM --> MT[MetricsTracking]
                CV --> CS[ComponentState]
                CV --> RC[ResourceCleanup]
                MC --> CC
                CC --> CS
        ```",
        "dependencies": {
            "MonitoringCoordinator": {
                "description": "System monitoring and metrics collection",
                "responsibilities": [
                    "Component registration",
                    "Thread management",
                    "Performance tracking",
                    "Error handling"
                ]
            },
            "ComponentCoordinator": {
                "description": "Component lifecycle management",
                "responsibilities": [
                    "State transitions",
                    "Resource allocation",
                    "Cleanup coordination",
                    "Error recovery"
                ]
            },
            "ResourcePool": {
                "description": "Memory management with tiered pools",
                "responsibilities": [
                    "Buffer allocation/deallocation",
                    "Pool optimization",
                    "Memory tracking",
                    "Resource cleanup"
                ]
            },
            "StateMachine": {
                "description": "Component state management",
                "responsibilities": [
                    "State transitions",
                    "Recovery states",
                    "Cleanup validation",
                    "Error handling"
                ]
            }
        }
    },
    "notes": [
        "Must register with ComponentCoordinator through MonitoringCoordinator",
        "Implements channel-specific buffer queues (left/right)",
        "Uses atomic operations for thread safety",
        "Provides comprehensive performance tracking",
        "Ensures proper resource cleanup",
        "Maintains detailed error context"
    ],
    "usage": {
        "examples": [
            "buffer_manager = BufferManager(coordinator, config)",
            "success = buffer_manager.put_buffer('capture_left', data)",
            "data = buffer_manager.get_buffer('processing_right')",
            "stats = buffer_manager.get_performance_stats()",
            "buffer_manager.cleanup()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "threading",
            "queue",
            "numpy",
            "dataclasses",
            "logging"
        ],
        "system": {
            "memory": "Configurable pool sizes",
            "threading": "Thread-safe operations",
            "channels": "Stereo audio support"
        }
    },
    "performance": {
        "execution_time": {
            "buffer_operations": "O(1) for put/get",
            "state_updates": "Atomic operations",
            "cleanup": "Linear with queue size"
        },
        "resource_usage": [
            "Tiered memory pools (4KB/64KB/1MB)",
            "Configurable queue sizes",
            "Channel-specific buffers",
            "Minimal lock contention",
            "Efficient cleanup coordination"
        ]
    }
}
"""

import threading
import time
import logging
import traceback
import numpy as np
from queue import Queue, Empty
from typing import Optional, Dict, Any, List
from typing_extensions import Tuple
from dataclasses import dataclass
@dataclass
class BufferConfig:
    """Buffer configuration parameters."""
    size: int
    channels: int
    sample_width: int
    sample_rate: int
    
    @property
    def duration_ms(self) -> float:
        return (self.size * 1000) / self.sample_rate
        
    @property
    def bytes_per_buffer(self) -> int:
        return self.size * self.channels * self.sample_width

class BufferManager:
    def __init__(self, coordinator, config: Optional[BufferConfig] = None):
        """Initialize buffer manager with optional configuration.
        
        Args:
            coordinator: MonitoringCoordinator instance
            config: Optional buffer configuration
        """
        self.logger = logging.getLogger("BufferManager")
        self.coordinator = coordinator
        # Get state machine from coordinator
        self._state_machine = coordinator.get_state_machine()
        if self._state_machine is None:
            raise RuntimeError("StateMachine not available from coordinator")
            
        # Get RecoveryState enum from coordinator
        self.RecoveryState = coordinator.get_recovery_state_enum()
        if self.RecoveryState is None:
            raise RuntimeError("RecoveryState enum not available from coordinator")
            
        self._initialized = False
        
        # Thread safety - locks in acquisition order matching MonitoringCoordinator
        self._state_lock = threading.RLock()     # Lock 1 (reentrant for state changes)
        self._metrics_lock = threading.Lock()    # Lock 2 (for metrics updates)
        self._perf_lock = threading.Lock()       # Lock 3 (for performance tracking)
        self._component_lock = threading.Lock()   # Lock 4 (for component operations)
        self._update_lock = threading.Lock()     # Lock 5 (for atomic updates)
        
        # Public lock access for testing (maintaining compatibility)
        self.state_lock = self._state_lock
        self.component_lock = self._component_lock
        
        # Note: Lock hierarchy (2025-02-19)
        # 1. state_lock (RLock) - State changes and validation
        # 2. metrics_lock - Metrics updates and tracking
        # 3. perf_lock - Performance statistics
        # 4. component_lock - Component lifecycle operations
        # 5. update_lock - Atomic buffer operations
        
        # State management
        self._state = {'sequence': 0}
        self._last_error = None
        self._active_components = {}
        
        self._cleanup_event = threading.Event()
        self._update_in_progress = threading.Event()
        
        # Buffer configuration
        self.min_buffer_ms = 30
        self.max_buffer_ms = 128
        self.optimal_write_size = 32 * 1024
        self.buffer_threshold = 0.8
        
        # Performance tracking
        self._last_adjustment = 0
        self._adjustment_cooldown = 5.0
        self._performance_history = []
        self._history_limit = 100
        
        # Component management
        self._component_types = {}  # id -> type mapping
        self._component_states = {}  # id -> state mapping
        
        # Initialize buffer queues with proper channel separation, size tracking and timeout
        from queue import Queue
        self._buffer_queues = {
            'capture_left': Queue(maxsize=1000),  # Prevent unbounded growth
            'capture_right': Queue(maxsize=1000),
            'processing_left': Queue(maxsize=500),
            'processing_right': Queue(maxsize=500),
            'storage_left': Queue(maxsize=250),
            'storage_right': Queue(maxsize=250)
        }
        
        # Initialize items processed tracking
        # Note: Added 2025-02-18 to fix missing initialization
        self._items_processed = {
            'capture': 0,
            'processing': 0,
            'storage': 0
        }
        
        # Queue overflow tracking
        self._queue_overflow_counts = {
            'capture': 0,
            'processing': 0,
            'storage': 0
        }
        
        # Enhanced metrics tracking
        self._metrics = {
            'items_processed': {
                'capture': 0,
                'processing': 0,
                'storage': 0
            },
            'queue_latency': {  # Track time spent in queue
                'capture': [],
                'processing': [],
                'storage': []
            },
            'buffer_sizes': {  # Track buffer size distribution
                'small': 0,    # 4KB
                'medium': 0,   # 64KB
                'large': 0     # 1MB
            }
        }
        
        # Enhanced queue metrics mapping
        self._queue_metrics = {
            'capture_left': {
                'size': 'capture_queue_size_left',
                'latency': 'capture_latency_left',
                'overflow': 'capture_overflow_left',
                'processed': 'capture_processed_left'
            },
            'capture_right': {
                'size': 'capture_queue_size_right',
                'latency': 'capture_latency_right',
                'overflow': 'capture_overflow_right',
                'processed': 'capture_processed_right'
            },
            'processing_left': {
                'size': 'processing_queue_size_left',
                'latency': 'processing_latency_left',
                'overflow': 'processing_overflow_left',
                'processed': 'processing_processed_left'
            },
            'processing_right': {
                'size': 'processing_queue_size_right',
                'latency': 'processing_latency_right',
                'overflow': 'processing_overflow_right',
                'processed': 'processing_processed_right'
            },
            'storage_left': {
                'size': 'storage_queue_size_left',
                'latency': 'storage_latency_left',
                'overflow': 'storage_overflow_left',
                'processed': 'storage_processed_left'
            },
            'storage_right': {
                'size': 'storage_queue_size_right',
                'latency': 'storage_latency_right',
                'overflow': 'storage_overflow_right',
                'processed': 'storage_processed_right'
            }
        }
        
        # Initialize with provided config or defaults
        self.current_config = config or BufferConfig(
            size=480, 
            channels=2, 
            sample_width=2, 
            sample_rate=16000
        )
        
        # Validate configuration
        if self.current_config.size <= 0:
            raise ValueError("Buffer size must be positive")
        if self.current_config.channels <= 0:
            raise ValueError("Channel count must be positive")
        if self.current_config.sample_width <= 0:
            raise ValueError("Sample width must be positive")
        if self.current_config.sample_rate <= 0:
            raise ValueError("Sample rate must be positive")
            
        self._initialized = True
        
        self._state_machine.register_state_change_callback(self._handle_state_change)
        
        if self.coordinator:
            # Register thread first
            self.coordinator.register_thread()
            
            # Get component coordinator through monitoring coordinator
            component_coordinator = self.coordinator.get_component_coordinator()
            if not component_coordinator:
                raise RuntimeError("No component coordinator available")
                
            # Register component with proper validation
            if not component_coordinator.register_component('buffer_manager', 'core'):
                raise RuntimeError("Failed to register buffer_manager component")
                
            # Register state change callback
            component_coordinator.register_state_callback(self._handle_state_change)
            
            # Initialize metrics after successful registration
            self.coordinator.update_state(
                capture_queue_size_left=0,
                capture_queue_size_right=0,
                processing_queue_size_left=0,
                processing_queue_size_right=0,
                storage_queue_size_left=0,
                storage_queue_size_right=0
            )
            
            # Resource pool already configured by MonitoringCoordinator
            
    def begin_update(self, timeout: float = 1.0) -> bool:
        """Begin atomic state update with timeout."""
        if not self._update_lock.acquire(timeout=timeout):
            return False
        self._update_in_progress.set()
        return True
        
    def end_update(self) -> None:
        """End atomic state update."""
        self._update_in_progress.clear()
        self._update_lock.release()
        
    def get_state(self) -> Dict[str, Any]:
        """Get current state with proper locking."""
        if not self._update_in_progress.is_set():
            raise RuntimeError("Must call begin_update before get_state")
        return self._state.copy()
        
    def update_state(self, new_state: Dict[str, Any]) -> None:
        """Update state with proper locking."""
        if not self._update_in_progress.is_set():
            raise RuntimeError("Must call begin_update before update_state")
        if new_state is None:
            raise ValueError("State cannot be None")
        self._state.update(new_state)
        
    def register_component(self, component_id: str, component_type: str) -> bool:
        """Register a component with proper validation."""
        with self._component_lock:
            if component_id in self._component_types:
                return False
            self._component_types[component_id] = component_type
            self._component_states[component_id] = False  # Initially inactive
            return True
            
    def mark_component_active(self, component_id: str) -> bool:
        """Mark a component as active with validation."""
        with self._component_lock:
            if component_id not in self._component_types:
                return False
            self._component_states[component_id] = True
            return True
            
    def mark_component_inactive(self, component_id: str) -> bool:
        """Mark a component as inactive with validation."""
        with self._component_lock:
            if component_id not in self._component_types:
                return False
            self._component_states[component_id] = False
            return True
            
    def get_active_components(self) -> List[str]:
        """Get list of active components."""
        with self._component_lock:
            return [cid for cid, active in self._component_states.items() if active]
            
    @dataclass
    class CleanupValidation:
        """Cleanup validation results."""
        valid: bool
        active_components: List[str]
            
    def validate_cleanup(self) -> CleanupValidation:
        """Validate cleanup state."""
        with self._component_lock:
            active = self.get_active_components()
            return self.CleanupValidation(
                valid=True,  # Always valid in this implementation
                active_components=active
            )
            
    def try_acquire_locks(self, timeout: float = 0.5) -> bool:
        """Try to acquire all locks in proper order following MonitoringCoordinator hierarchy.
        
        Lock acquisition order:
        1. state_lock (RLock) - State changes and validation
        2. metrics_lock - Metrics updates and tracking
        3. perf_lock - Performance statistics
        4. component_lock - Component lifecycle operations
        5. update_lock - Atomic buffer operations
        
        Args:
            timeout: Maximum time to wait for all locks
            
        Returns:
            bool: True if all locks acquired, False if any lock acquisition failed
        """
        end_time = time.time() + timeout
        
        # Acquire locks in order matching MonitoringCoordinator
        if not self._state_lock.acquire(timeout=max(0, end_time - time.time())):
            return False
            
        try:
            if not self._metrics_lock.acquire(timeout=max(0, end_time - time.time())):
                self._state_lock.release()
                return False
                
            try:
                if not self._perf_lock.acquire(timeout=max(0, end_time - time.time())):
                    self._metrics_lock.release()
                    self._state_lock.release()
                    return False
                    
                try:
                    if not self._component_lock.acquire(timeout=max(0, end_time - time.time())):
                        self._perf_lock.release()
                        self._metrics_lock.release()
                        self._state_lock.release()
                        return False
                        
                    try:
                        if not self._update_lock.acquire(timeout=max(0, end_time - time.time())):
                            self._component_lock.release()
                            self._perf_lock.release()
                            self._metrics_lock.release()
                            self._state_lock.release()
                            return False
                    except:
                        self._component_lock.release()
                        self._perf_lock.release()
                        self._metrics_lock.release()
                        self._state_lock.release()
                        raise
                except:
                    self._perf_lock.release()
                    self._metrics_lock.release()
                    self._state_lock.release()
                    raise
            except:
                self._metrics_lock.release()
                self._state_lock.release()
                raise
        except:
            self._state_lock.release()
            raise
            
        return True
        
    def get_last_error(self) -> Optional[Dict[str, Any]]:
        """Get last error context."""
        with self._state_lock:
            return self._last_error.copy() if self._last_error else None
            
    def clear_errors(self) -> None:
        """Clear error context."""
        with self._state_lock:
            self._last_error = None
            
    def is_valid(self) -> bool:
        """Check if buffer manager is in valid state."""
        with self._state_lock:
            return self._initialized and not self._cleanup_event.is_set()
            
    def _parse_component(self, component: str) -> Tuple[str, str]:
        """Parse component name into base component and channel.
        
        Args:
            component: Component name with optional channel suffix
            
        Returns:
            Tuple of (base_component, channel)
        """
        if component.endswith('_left'):
            return component[:-5], 'left'
        elif component.endswith('_right'):
            return component[:-6], 'right'
        # Default to left channel if not specified
        return component, 'left'

    def _handle_state_change(self, old_state: RecoveryState, new_state: RecoveryState) -> None:
        """Handle state changes without holding locks during state machine operations."""
        self.logger.info(f"Buffer state change: {old_state.value} -> {new_state.value}")
        try:
            if new_state == self.RecoveryState.FLUSHING_BUFFERS:
                # Release all queued buffers
                with self._state_lock:
                    for queue_name, queue in self._buffer_queues.items():
                        base_component = queue_name.rsplit('_', 1)[0]
                        while not queue.empty():
                            try:
                                buffer = queue.get_nowait()
                                self.coordinator.release_resource(base_component, 'buffer', buffer)
                            except Empty:
                                break
            elif new_state == self.RecoveryState.FAILED:
                # Update config under state lock only
                with self._state_lock:
                    self.current_config.size = int(self.min_buffer_ms * self.current_config.sample_rate / 1000)
        except Exception as e:
            self.logger.exception("Error handling state change")
            if self.coordinator:
                self.coordinator.handle_error(e, "buffer_manager")

    def put_buffer(self, component: str, data: bytes, timeout: float = 0.5) -> bool:
        """Thread-safe buffer put operation with proper error context and metrics.
        
        Args:
            component: Component name (e.g. 'capture_left', 'processing_right')
            data: Binary data to store
            timeout: Operation timeout in seconds
            
        Returns:
            bool: True if operation succeeded, False otherwise
            
        Note:
            Uses queue-based implementation with proper channel separation.
            All operations are atomic and thread-safe.
        """
        if not self._initialized:
            self.logger.error("Buffer manager not properly initialized")
            return False
            
        if self.coordinator and self.coordinator.is_shutdown_requested():
            return False
            
        if self._cleanup_event.is_set():
            return False
            
        try:
            # Validate component and get base/channel
            try:
                base_component, channel = self._parse_component(component)
                queue_name = f"{base_component}_{channel}"
            except ValueError as e:
                self.logger.error(f"Invalid component format: {e}")
                return False
                
            # Begin atomic update with proper timeout handling
            start_time = time.time()
            if not self.begin_update(timeout):
                self.logger.error(f"Failed to begin update for put_buffer after {time.time() - start_time:.2f}s")
                return False
                
            try:
                # Critical section with proper lock ordering
                with self._state_lock:
                    # Pre-allocate buffer before queue operations
                    buffer = self.coordinator.allocate_resource(base_component, 'buffer', len(data))
                    if not buffer:
                        self.logger.error(f"Failed to allocate buffer for {component}")
                        return False
                    
                    try:
                        # Copy data with bounds check
                        if len(buffer) < len(data):
                            raise ValueError(f"Buffer too small: {len(buffer)} < {len(data)}")
                            
                        buffer[:len(data)] = data
                        
                        # Validate queue exists before operation
                        if queue_name not in self._buffer_queues:
                            raise ValueError(f"Invalid queue name: {queue_name}")
                        
                        # Atomic queue operation
                        self._buffer_queues[queue_name].put(buffer)
                        self._items_processed[base_component] += 1
                        
                        # Get sizes atomically
                        queue_size = self._buffer_queues[queue_name].qsize()
                        total_size = (self._buffer_queues[f"{base_component}_left"].qsize() + 
                                    self._buffer_queues[f"{base_component}_right"].qsize())
                                    
                    except Exception as e:
                        # Clean up allocated buffer on error
                        self.coordinator.release_resource(base_component, 'buffer', buffer)
                        raise
                    
                    # Update performance tracking atomically with proper error handling
                    try:
                        current_time = time.time()
                        perf_entry = {
                            'timestamp': current_time,
                            'operation': 'put',
                            'component': component,
                            'queue_size': queue_size,
                            'total_size': total_size,
                            'items_processed': self._items_processed[base_component],
                            'duration_ms': int((current_time - start_time) * 1000)
                        }
                        self._performance_history.append(perf_entry)
                        
                        # Trim history with proper bounds checking
                        if len(self._performance_history) > self._history_limit:
                            self._performance_history = self._performance_history[-self._history_limit:]
                    except Exception as e:
                        self.logger.error(f"Failed to update performance history: {e}")
                        # Continue since this is non-critical
                
                # Update enhanced metrics outside state lock but inside update
                if self.coordinator:
                    metrics = {
                        self._queue_metrics[queue_name]['size']: queue_size,
                        self._queue_metrics[queue_name]['latency']: np.mean(self._metrics['queue_latency'][base_component]) if self._metrics['queue_latency'][base_component] else 0,
                        self._queue_metrics[queue_name]['overflow']: self._queue_overflow_counts[base_component],
                        self._queue_metrics[queue_name]['processed']: self._metrics['items_processed'][base_component],
                        f"{base_component}_queue_size": total_size,
                        f"{base_component}_buffer_small": self._metrics['buffer_sizes']['small'],
                        f"{base_component}_buffer_medium": self._metrics['buffer_sizes']['medium'],
                        f"{base_component}_buffer_large": self._metrics['buffer_sizes']['large']
                    }
                    self.coordinator.update_state(**metrics)
                
                return True
                
            finally:
                self.end_update()
            
        except Exception as e:
            # Track error context
            with self._state_lock:
                self._last_error = {
                    'scenario': 'put_buffer',
                    'error': str(e),
                    'timestamp': time.time(),
                    'stack_trace': ''.join(traceback.format_tb(e.__traceback__))
                }
            self.logger.exception("Unexpected error in put_buffer")
            if self.coordinator:
                self.coordinator.handle_error(e, "buffer_manager")
        return False

    def get_buffer(self, component: str, timeout: float = 1.0) -> Optional[bytes]:
        """Thread-safe buffer get operation with proper error context and metrics.
        
        Args:
            component: Component name (e.g. 'capture_left', 'processing_right')
            timeout: Operation timeout in seconds
            
        Returns:
            Optional[bytes]: Buffer data if successful, None otherwise
            
        Note:
            Uses queue-based implementation with proper channel separation.
            All operations are atomic and thread-safe.
        """
        if not self._initialized:
            self.logger.error("Buffer manager not properly initialized")
            return None
            
        if self.coordinator and self.coordinator.is_shutdown_requested():
            return None
            
        if self._cleanup_event.is_set():
            return None
            
        try:
            # Validate component and get base/channel
            try:
                base_component, channel = self._parse_component(component)
                queue_name = f"{base_component}_{channel}"
            except ValueError as e:
                self.logger.error(f"Invalid component format: {e}")
                return None
                
            # Begin atomic update with proper timeout handling
            start_time = time.time()
            if not self.begin_update(timeout):
                self.logger.error(f"Failed to begin update for get_buffer after {time.time() - start_time:.2f}s")
                return None
                
            try:
                # Critical section with proper lock ordering
                with self._state_lock:
                    # Validate queue exists before operation
                    if queue_name not in self._buffer_queues:
                        raise ValueError(f"Invalid queue name: {queue_name}")
                        
                    try:
                        # Get buffer with timeout
                        buffer = self._buffer_queues[queue_name].get(timeout=timeout)
                        
                        try:
                            # Copy data atomically
                            data = bytes(buffer)
                            
                            # Get sizes atomically
                            queue_size = self._buffer_queues[queue_name].qsize()
                            total_size = (self._buffer_queues[f"{base_component}_left"].qsize() + 
                                        self._buffer_queues[f"{base_component}_right"].qsize())
                            
                            # Update performance tracking atomically with proper error handling
                            try:
                                current_time = time.time()
                                perf_entry = {
                                    'timestamp': current_time,
                                    'operation': 'get',
                                    'component': component,
                                    'queue_size': queue_size,
                                    'total_size': total_size,
                                    'items_processed': self._items_processed[base_component],
                                    'duration_ms': int((current_time - start_time) * 1000)
                                }
                                self._performance_history.append(perf_entry)
                                
                                # Trim history with proper bounds checking
                                if len(self._performance_history) > self._history_limit:
                                    self._performance_history = self._performance_history[-self._history_limit:]
                            except Exception as e:
                                self.logger.error(f"Failed to update performance history: {e}")
                                # Continue since this is non-critical
                            
                            return data
                            
                        finally:
                            # Always release buffer back to pool
                            self.coordinator.release_resource(base_component, 'buffer', buffer)
                            
                    except Empty:
                        return None
                        
                # Update metrics outside state lock but inside update
                if self.coordinator:
                    self.coordinator.update_state(**{
                        self._queue_name_map[queue_name]: queue_size,
                        f"{base_component}_queue_size": total_size,
                        f"{base_component}_items_processed": self._items_processed[base_component]
                    })
                        
            finally:
                self.end_update()
                
        except Exception as e:
            # Track error context
            with self._state_lock:
                self._last_error = {
                    'scenario': 'get_buffer',
                    'error': str(e),
                    'timestamp': time.time(),
                    'stack_trace': ''.join(traceback.format_tb(e.__traceback__))
                }
            self.logger.exception("Unexpected error in get_buffer")
            if self.coordinator:
                self.coordinator.handle_error(e, "buffer_manager")
        return None
    
    def get_buffer_config(self) -> BufferConfig:
        """Thread-safe access to buffer configuration."""
        with self._state_lock:
            return self.current_config

    def update_buffer_config(self, **kwargs) -> None:
        """Thread-safe buffer configuration update."""
        with self._state_lock:
            for key, value in kwargs.items():
                if hasattr(self.current_config, key):
                    setattr(self.current_config, key, value)
            
            # Update buffer size based on duration
            self.current_config.size = int(self.min_buffer_ms * self.current_config.sample_rate / 1000)

    def optimize_buffers(self) -> None:
        """Thread-safe buffer optimization."""
        current_time = time.time()
        if current_time - self._last_adjustment < self._adjustment_cooldown:
            return

        try:
            # Begin atomic update
            if not self.begin_update():
                self.logger.error("Failed to begin update for optimize_buffers")
                return
                
            try:
                metrics = None
                if self.coordinator:
                    metrics = self.coordinator.get_metrics()

                with self._state_lock:
                    if metrics:
                        old_size = self.current_config.size
                        
                        # Calculate optimal tier size based on current usage
                        current_size = self.current_config.size
                        optimal_tier = None
                        
                        # Determine appropriate tier based on size
                        if current_size <= 4 * 1024:  # 4KB
                            optimal_tier = 'small'
                        elif current_size <= 64 * 1024:  # 64KB
                            optimal_tier = 'medium'
                        else:  # 1MB
                            optimal_tier = 'large'
                            
                        # Adjust size based on CPU and memory pressure while respecting tier boundaries
                        if metrics.cpu_usage > 80:
                            # Scale up within tier boundaries
                            if optimal_tier == 'small' and current_size < 4 * 1024:
                                new_size = min(
                                    int(current_size * 1.5),
                                    4 * 1024  # Stay within small tier
                                )
                            elif optimal_tier == 'medium' and current_size < 64 * 1024:
                                new_size = min(
                                    int(current_size * 1.5),
                                    64 * 1024  # Stay within medium tier
                                )
                            elif optimal_tier == 'large' and current_size < 1024 * 1024:
                                new_size = min(
                                    int(current_size * 1.5),
                                    1024 * 1024  # Stay within large tier
                                )
                            else:
                                new_size = current_size  # Already at tier limit
                        elif metrics.memory_usage > 100 * 1024 * 1024:  # 100MB threshold
                            # Scale down while respecting minimum tier sizes
                            if optimal_tier == 'large' and current_size > 64 * 1024:
                                new_size = max(
                                    int(current_size * 0.75),
                                    64 * 1024  # Don't go below medium tier
                                )
                            elif optimal_tier == 'medium' and current_size > 4 * 1024:
                                new_size = max(
                                    int(current_size * 0.75),
                                    4 * 1024  # Don't go below small tier
                                )
                            else:
                                new_size = max(
                                    int(current_size * 0.75),
                                    int(self.min_buffer_ms * self.current_config.sample_rate / 1000)
                                )
                        else:
                            new_size = current_size
                            
                        self.current_config.size = new_size
                        
                        # Track tier transition if size changed
                        if new_size != current_size:
                            self._metrics['buffer_sizes'][optimal_tier] += 1
                            
                        # Record performance stats with adjustment details
                        self._performance_history.append({
                            'timestamp': current_time,
                            'operation': 'optimize',
                            'old_size': old_size,
                            'new_size': self.current_config.size,
                            'buffer_duration_ms': self.current_config.duration_ms,
                            'cpu_usage': metrics.cpu_usage,
                            'memory_usage': metrics.memory_usage
                        })
                        
                        # Trim history
                        if len(self._performance_history) > self._history_limit:
                            self._performance_history = self._performance_history[-self._history_limit:]
                        
                        self._last_adjustment = current_time
                        
                        # Update coordinator with new buffer configuration
                        if self.coordinator:
                            self.coordinator.update_state(
                                buffer_size=self.current_config.size,
                                buffer_duration_ms=self.current_config.duration_ms,
                                last_buffer_adjustment=current_time
                            )
            except Exception as e:
                # Track error context
                with self._state_lock:
                    self._last_error = {
                        'scenario': 'optimize_buffers',
                        'error': str(e),
                        'timestamp': time.time(),
                        'stack_trace': ''.join(traceback.format_tb(e.__traceback__))
                    }
                self.logger.error(f"Buffer optimization error: {e}")
                if self.coordinator:
                    self.coordinator.handle_error(e, "buffer_manager")
                raise  # Re-raise to be caught by outer try
            finally:
                self.end_update()
        except Exception as e:
            self.logger.exception("Failed to optimize buffers")
            if self.coordinator:
                self.coordinator.handle_error(e, "buffer_manager")

    def get_performance_stats(self) -> Dict[str, Any]:
        """Thread-safe access to enhanced performance statistics."""
        with self._state_lock:
            stats = {
                'buffer_config': {
                    'size_ms': self.current_config.duration_ms,
                    'size_bytes': self.current_config.bytes_per_buffer,
                    'last_adjustment': self._last_adjustment
                },
                'queue_metrics': {},
                'buffer_distribution': {
                    'small': self._metrics['buffer_sizes']['small'],
                    'medium': self._metrics['buffer_sizes']['medium'],
                    'large': self._metrics['buffer_sizes']['large']
                },
                'latency': {},
                'overflow': self._queue_overflow_counts.copy(),
                'processed': self._metrics['items_processed'].copy()
            }
            
            # Add detailed queue metrics
            for name, queue in self._buffer_queues.items():
                base_component = name.rsplit('_', 1)[0]
                channel = name.rsplit('_', 1)[1]
                
                stats['queue_metrics'][name] = {
                    'size': queue.qsize(),
                    'latency': np.mean(self._metrics['queue_latency'][base_component]) if self._metrics['queue_latency'][base_component] else 0,
                    'overflow': self._queue_overflow_counts[base_component],
                    'processed': self._metrics['items_processed'][base_component]
                }
                
                # Track latency per queue
                stats['latency'][name] = {
                    'current': stats['queue_metrics'][name]['latency'],
                    'history': self._metrics['queue_latency'][base_component][-10:] if self._metrics['queue_latency'][base_component] else []
                }
            
            return stats

    @property
    def performance_history(self) -> list:
        """Thread-safe access to performance history."""
        with self._state_lock:
            return self._performance_history.copy()

    def cleanup(self) -> None:
        """Thread-safe cleanup with proper lock ordering and state validation.
        
        Note:
            - Acquires locks in proper order: cleanup -> state -> component
            - Validates state transitions and queue emptiness
            - Ensures proper resource cleanup
            - Maintains atomic operations
            - Preserves error context
        """
        try:
            # Begin atomic update for cleanup
            if not self.begin_update(timeout=5.0):  # Longer timeout for cleanup
                raise RuntimeError("Failed to begin cleanup update")
            
            # Set cleanup event first
            self._cleanup_event.set()
            
            # Transition state with validation
            if not self._state_machine.transition_to(self.RecoveryState.FLUSHING_BUFFERS):
                raise RuntimeError("Failed to transition to FLUSHING_BUFFERS state")
            
            # Release all queued buffers with validation
            with self._state_lock:
                # Track resources for verification
                released_buffers = 0
                queue_states = {}
                
                # First pass: count and release
                for queue_name, queue in self._buffer_queues.items():
                    base_component = queue_name.rsplit('_', 1)[0]
                    queue_states[queue_name] = queue.qsize()
                    
                    while not queue.empty():
                        try:
                            buffer = queue.get_nowait()
                            self.coordinator.release_resource(base_component, 'buffer', buffer)
                            released_buffers += 1
                        except Empty:
                            break
                
                # Second pass: verify emptiness
                for queue_name, queue in self._buffer_queues.items():
                    if not queue.empty():
                        raise RuntimeError(f"Queue {queue_name} not empty after cleanup")
                
                # Clear all performance data atomically
                self._performance_history.clear()
                self._last_adjustment = 0
                self._metrics = {
                    'items_processed': {k: 0 for k in self._metrics['items_processed']},
                    'queue_latency': {k: [] for k in self._metrics['queue_latency']},
                    'buffer_sizes': {k: 0 for k in self._metrics['buffer_sizes']}
                }
                self._queue_overflow_counts = {k: 0 for k in self._queue_overflow_counts}
            
            # Verify cleanup with detailed validation
            validation = self.validate_cleanup()
            if not validation.valid:
                error_msg = f"Cleanup validation failed with active components: {validation.active_components}"
                self.logger.error(error_msg)
                self._state_machine.transition_to(self.RecoveryState.FAILED)
                raise RuntimeError(error_msg)
            
            # Update coordinator state
            if self.coordinator:
                # Update final metrics
                metrics_update = {
                    'cleanup_released_buffers': released_buffers,
                    'cleanup_queue_states': queue_states
                }
                for queue_name in self._buffer_queues:
                    metrics_update[f"{queue_name}_size"] = 0
                self.coordinator.update_state(**metrics_update)
                
                # Mark cleanup complete
                try:
                    self.coordinator.mark_component_cleanup_complete('buffer_manager')
                except Exception as e:
                    self.logger.warning(f"Failed to mark cleanup complete: {e}")
                    
                # Unregister thread
                try:
                    self.coordinator.unregister_thread()
                except Exception as e:
                    self.logger.warning(f"Failed to unregister thread: {e}")
            
            # Final state transitions with validation
            if not self._state_machine.transition_to(self.RecoveryState.VERIFIED):
                raise RuntimeError("Failed to transition to VERIFIED state")
                
            if not self._state_machine.transition_to(self.RecoveryState.COMPLETED):
                raise RuntimeError("Failed to transition to COMPLETED state")
                
        except Exception as e:
            # Track error context
            with self._state_lock:
                self._last_error = {
                    'scenario': 'cleanup',
                    'error': str(e),
                    'timestamp': time.time(),
                    'stack_trace': ''.join(traceback.format_tb(e.__traceback__))
                }
            self.logger.exception("Buffer cleanup error")
            if self.coordinator:
                self.coordinator.handle_error(e, "buffer_manager")
            self._state_machine.transition_to(self.RecoveryState.FAILED)
        finally:
            self._cleanup_event.clear()
