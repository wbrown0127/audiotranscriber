"""
COMPONENT_NOTES:
{
    "name": "StateMachine",
    "type": "Core Component",
    "description": "Thread-safe state machine that manages recovery process states with enhanced validation, history tracking, state change notifications, and performance metrics",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                SM[StateMachine] --> RS[RecoveryState]
                SM --> ST[StateTransition]
                SM --> SE[StateEvent]
                SM --> VL[ValidationLayer]
                SM --> HT[HistoryTracker]
                SM --> NC[NotificationCenter]
                SM --> PM[PerformanceMetrics]
                SM --> RP[ResourcePool]
                SM --> CC[ComponentCoordinator]
                SM --> BM[BufferManager]
        ```",
        "dependencies": {
            "ResourcePool": "Resource allocation and cleanup",
            "ComponentCoordinator": "Component health validation",
            "BufferManager": "Staged cleanup coordination",
            "PerformanceMetrics": "State transition tracking"
        }
    },
    "notes": [
        "Enhanced 2025-02-19:",
        "- Added performance metrics for state transitions",
        "- Implemented staged cleanup with BufferManager",
        "- Added channel-aware state validation",
        "- Enhanced error context preservation",
        "- Added resource pool integration",
        "- Improved state validation with health checks",
        "- Added retry mechanism for coordinator validation",
        "- Enhanced rollback mechanisms",
        "- Improved logging and error handling"
    ]
}
"""

import enum
import logging
import threading
import time
import numpy as np
from typing import Dict, List, Optional, Set, Callable, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

class RecoveryState(enum.Enum):
    """States for the recovery process with enhanced validation."""
    IDLE = "idle"
    INITIATING = "initiating"
    STOPPING_CAPTURE = "stopping_capture"
    STOPPING_CAPTURE_LEFT = "stopping_capture_left"   # Channel-specific states
    STOPPING_CAPTURE_RIGHT = "stopping_capture_right"
    FLUSHING_BUFFERS = "flushing_buffers"
    FLUSHING_BUFFERS_LEFT = "flushing_buffers_left"  # Channel-specific states
    FLUSHING_BUFFERS_RIGHT = "flushing_buffers_right"
    REINITIALIZING = "reinitializing"
    VERIFYING = "verifying"
    VERIFYING_RESOURCES = "verifying_resources"
    VERIFYING_COMPONENTS = "verifying_components"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class PerformanceMetrics:
    """Performance metrics for state transitions."""
    transition_count: int = 0
    successful_transitions: int = 0
    failed_transitions: int = 0
    total_transition_time: float = 0.0
    transition_times: Dict[Tuple[str, str], List[float]] = field(default_factory=dict)
    error_counts: Dict[str, int] = field(default_factory=dict)
    
    def record_transition(self, from_state: str, to_state: str, duration: float, success: bool) -> None:
        """Record a state transition with timing."""
        self.transition_count += 1
        if success:
            self.successful_transitions += 1
        else:
            self.failed_transitions += 1
        
        self.total_transition_time += duration
        key = (from_state, to_state)
        if key not in self.transition_times:
            self.transition_times[key] = []
        self.transition_times[key].append(duration)
        
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        stats = {
            'transition_count': self.transition_count,
            'success_rate': (self.successful_transitions / self.transition_count 
                           if self.transition_count > 0 else 0),
            'avg_transition_time': (self.total_transition_time / self.transition_count 
                                  if self.transition_count > 0 else 0),
            'transition_times': {},
            'error_counts': self.error_counts
        }
        
        for (from_state, to_state), times in self.transition_times.items():
            if times:
                stats['transition_times'][f'{from_state}->{to_state}'] = {
                    'avg': np.mean(times),
                    'min': np.min(times),
                    'max': np.max(times),
                    'count': len(times)
                }
        
        return stats

@dataclass
class StateTransition:
    """Represents a state transition with enhanced validation rules."""
    from_state: RecoveryState
    to_state: RecoveryState
    validation_fn: Optional[Callable[[], bool]] = None
    rollback_fn: Optional[Callable[[], None]] = None
    cleanup_fn: Optional[Callable[[], None]] = None  # Added for cleanup coordination
    resource_check: Optional[Callable[[], bool]] = None  # Added for resource validation
    component_check: Optional[Callable[[], bool]] = None  # Added for component health

@dataclass
class StateEvent:
    """Records a state change event with enhanced context."""
    timestamp: float
    from_state: RecoveryState
    to_state: RecoveryState
    success: bool
    error: Optional[str] = None
    duration: float = 0.0  # Added for performance tracking
    resource_state: Optional[Dict[str, Any]] = None  # Added for resource tracking
    component_state: Optional[Dict[str, Any]] = None  # Added for component state

class StateMachine:
    """Thread-safe state machine for managing recovery process states with enhanced capabilities."""
    
    def __init__(self, initial_state: RecoveryState = RecoveryState.IDLE,
                 coordinator = None):
        """Initialize state machine with coordinator integration.
        
        Args:
            initial_state: Initial recovery state
            coordinator: MonitoringCoordinator instance for resource management
        """
        self.logger = logging.getLogger("StateMachine")
        self._current_state = initial_state
        self._history: List[StateEvent] = []
        self._metrics = PerformanceMetrics()
        
        if coordinator is None:
            raise RuntimeError("MonitoringCoordinator is required")
        self.coordinator = coordinator
        
        # Get required components through coordinator
        self._resource_pool = coordinator.get_resource_pool()
        self._component_coordinator = coordinator.get_component_coordinator()
        self._buffer_manager = coordinator.get_buffer_manager()
        
        if self._resource_pool is None:
            raise RuntimeError("ResourcePool not available from coordinator")
        if self._component_coordinator is None:
            raise RuntimeError("ComponentCoordinator not available from coordinator")
        if self._buffer_manager is None:
            raise RuntimeError("BufferManager not available from coordinator")
        
        # Locks in acquisition order
        self._state_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._callbacks_lock = threading.Lock()
        self._invariants_lock = threading.Lock()
        self._validators_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        
        # Cleanup coordination
        self._cleanup_stage = 0
        self._cleanup_event = threading.Event()
        
        # Enhanced callbacks with error context
        self._state_change_callbacks: List[Callable[[RecoveryState, RecoveryState, Optional[str]], None]] = []
        self._coordinator_callback: Optional[Callable[[RecoveryState, RecoveryState, bool], None]] = None
        self._transition_retry_count = 2
        self._transition_retry_delay = 0.05
        
        # Enhanced invariants with resource and component checks
        self._state_invariants: Dict[RecoveryState, List[Callable[[], bool]]] = {}
        
        # Enhanced state transitions with channel awareness
        self._valid_transitions: Dict[RecoveryState, Set[RecoveryState]] = {
            RecoveryState.IDLE: {
                RecoveryState.INITIATING,
                RecoveryState.FAILED
            },
            RecoveryState.INITIATING: {
                RecoveryState.STOPPING_CAPTURE,
                RecoveryState.STOPPING_CAPTURE_LEFT,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.STOPPING_CAPTURE: {
                RecoveryState.FLUSHING_BUFFERS,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.STOPPING_CAPTURE_LEFT: {
                RecoveryState.STOPPING_CAPTURE_RIGHT,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.STOPPING_CAPTURE_RIGHT: {
                RecoveryState.FLUSHING_BUFFERS,
                RecoveryState.FLUSHING_BUFFERS_LEFT,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.FLUSHING_BUFFERS: {
                RecoveryState.REINITIALIZING,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.FLUSHING_BUFFERS_LEFT: {
                RecoveryState.FLUSHING_BUFFERS_RIGHT,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.FLUSHING_BUFFERS_RIGHT: {
                RecoveryState.REINITIALIZING,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.REINITIALIZING: {
                RecoveryState.VERIFYING,
                RecoveryState.VERIFYING_RESOURCES,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.VERIFYING_RESOURCES: {
                RecoveryState.VERIFYING_COMPONENTS,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.VERIFYING_COMPONENTS: {
                RecoveryState.VERIFYING,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.VERIFYING: {
                RecoveryState.COMPLETED,
                RecoveryState.FAILED,
                RecoveryState.IDLE
            },
            RecoveryState.COMPLETED: {
                RecoveryState.IDLE,
                RecoveryState.FAILED
            },
            RecoveryState.FAILED: {
                RecoveryState.IDLE
            }
        }
        
        # Custom transition validators
        self._transition_validators: Dict[tuple[RecoveryState, RecoveryState], StateTransition] = {}
    
    def register_state_change_callback(self, callback: Callable[[RecoveryState, RecoveryState], None]) -> None:
        """Thread-safe registration of state change callback."""
        with self._callbacks_lock:
            self._state_change_callbacks.append(callback)
    
    def _notify_state_change(self, old_state: RecoveryState, new_state: RecoveryState) -> None:
        """Thread-safe notification of state change to all registered callbacks."""
        with self._callbacks_lock:
            for callback in self._state_change_callbacks:
                try:
                    callback(old_state, new_state)
                except Exception as e:
                    self.logger.error(f"Error in state change callback: {e}")
    
    def add_state_invariant(self, state: RecoveryState, invariant_fn: Callable[[], bool]) -> None:
        """Thread-safe addition of state invariant."""
        with self._invariants_lock:
            if state not in self._state_invariants:
                self._state_invariants[state] = []
            self._state_invariants[state].append(invariant_fn)
    
    def _check_invariants(self, state: RecoveryState) -> bool:
        """Thread-safe check of state invariants."""
        with self._invariants_lock:
            if state not in self._state_invariants:
                return True
            
            for invariant_fn in self._state_invariants[state]:
                try:
                    if not invariant_fn():
                        return False
                except Exception as e:
                    self.logger.error(f"Error checking invariant: {e}")
                    return False
            return True
    
    def _record_transition(self, from_state: RecoveryState, to_state: RecoveryState, 
                         success: bool, error: Optional[str] = None) -> None:
        """Thread-safe recording of state transition."""
        event = StateEvent(
            timestamp=datetime.now().timestamp(),
            from_state=from_state,
            to_state=to_state,
            success=success,
            error=error
        )
        with self._history_lock:
            self._history.append(event)
    
    def add_transition_validator(self, transition: StateTransition) -> None:
        """Thread-safe addition of transition validator."""
        with self._validators_lock:
            key = (transition.from_state, transition.to_state)
            self._transition_validators[key] = transition
    
    def set_coordinator_callback(self, callback: Callable[[RecoveryState, RecoveryState, bool], None]) -> None:
        """Allow MonitoringCoordinator to register a callback without breaking existing patterns."""
        self._coordinator_callback = callback

    def _validate_transition(self, from_state: RecoveryState, to_state: RecoveryState) -> bool:
        """Validate if transition is allowed with enhanced error handling and logging."""
        # First check coordinator if available
        if self._coordinator_callback:
            for attempt in range(self._transition_retry_count):
                try:
                    if not self._coordinator_callback(from_state, to_state, True):
                        self.logger.warning(
                            f"State transition {from_state} -> {to_state} blocked by Coordinator "
                            f"(attempt {attempt + 1}/{self._transition_retry_count})"
                        )
                        if attempt < self._transition_retry_count - 1:
                            time.sleep(self._transition_retry_delay)
                            continue
                        self._record_transition(
                            from_state,
                            to_state,
                            success=False,
                            error=f"Coordinator validation failed after {self._transition_retry_count} attempts"
                        )
                        return False
                    break  # Validation succeeded
                except Exception as e:
                    self.logger.error(
                        f"Coordinator validation error during {from_state} -> {to_state}: {e} "
                        f"(attempt {attempt + 1}/{self._transition_retry_count})"
                    )
                    if attempt < self._transition_retry_count - 1:
                        time.sleep(self._transition_retry_delay)
                        continue
                    self._record_transition(
                        from_state,
                        to_state,
                        success=False,
                        error=f"Coordinator validation error: {str(e)}"
                    )
                    return False

        # Check if transition is valid
        if to_state not in self._valid_transitions[from_state]:
            error_msg = f"Invalid transition: {from_state} -> {to_state}"
            self.logger.error(error_msg)
            self._record_transition(from_state, to_state, success=False, error=error_msg)
            return False
            
        # Enhanced invariant checking with detailed logging
        if not self._check_invariants(to_state):
            error_msg = f"State invariants not satisfied for transition {from_state} -> {to_state}"
            self.logger.error(error_msg)
            self._record_transition(from_state, to_state, success=False, error=error_msg)
            return False
            
        # Check custom validator with enhanced error handling
        key = (from_state, to_state)
        if key in self._transition_validators:
            validator = self._transition_validators[key]
            try:
                # Check resource validation first
                if validator.resource_check and not validator.resource_check():
                    error_msg = f"Resource validation failed for {from_state} -> {to_state}"
                    self.logger.error(error_msg)
                    self._record_transition(from_state, to_state, success=False, error=error_msg)
                    return False
                    
                # Check component health
                if validator.component_check and not validator.component_check():
                    error_msg = f"Component health check failed for {from_state} -> {to_state}"
                    self.logger.error(error_msg)
                    self._record_transition(from_state, to_state, success=False, error=error_msg)
                    return False
                    
                # Run cleanup if needed
                if validator.cleanup_fn:
                    try:
                        validator.cleanup_fn()
                    except Exception as e:
                        error_msg = f"Cleanup failed for {from_state} -> {to_state}: {e}"
                        self.logger.error(error_msg)
                        self._record_transition(from_state, to_state, success=False, error=error_msg)
                        return False
                
                # Final validation check
                if validator.validation_fn and not validator.validation_fn():
                    error_msg = f"Validation failed for {from_state} -> {to_state}"
                    self.logger.error(error_msg)
                    self._record_transition(from_state, to_state, success=False, error=error_msg)
                    return False
                    
            except Exception as e:
                error_msg = f"Validation error for {from_state} -> {to_state}: {type(e).__name__}: {str(e)}"
                self.logger.error(error_msg)
                self._record_transition(from_state, to_state, success=False, error=error_msg)
                return False
        
        return True
    
    def transition_to(self, new_state: RecoveryState) -> bool:
        """Thread-safe attempt to transition to a new state with enhanced error handling."""
        with self._state_lock:
            old_state = self._current_state
            start_time = time.time()
            
            try:
                # Special case: Always allow transition to FAILED state
                if new_state == RecoveryState.FAILED:
                    self._current_state = new_state
                    duration = time.time() - start_time
                    self._record_transition(old_state, new_state, success=True)
                    self._notify_state_change(old_state, new_state)
                    with self._metrics_lock:
                        self._metrics.record_transition(
                            old_state.value, new_state.value, duration, True
                        )
                    return True
                
                # Enhanced validation with detailed logging
                self.logger.info(f"Attempting state transition: {old_state} -> {new_state}")
                
                if not self._validate_transition(old_state, new_state):
                    self.logger.error(
                        f"State transition validation failed: {old_state} -> {new_state}"
                    )
                    duration = time.time() - start_time
                    with self._metrics_lock:
                        self._metrics.record_transition(
                            old_state.value, new_state.value, duration, False
                        )
                    # Attempt rollback on validation failure
                    self._rollback_transition(new_state)
                    return False
                
                # Perform transition
                self._current_state = new_state
                duration = time.time() - start_time
                
                # Record successful transition
                self._record_transition(
                    old_state, 
                    new_state, 
                    success=True,
                    duration=duration,
                    resource_state=self._get_resource_state(),
                    component_state=self._get_component_state()
                )
                
                # Update metrics
                with self._metrics_lock:
                    self._metrics.record_transition(
                        old_state.value, new_state.value, duration, True
                    )
                
                # Notify callbacks
                self._notify_state_change(old_state, new_state)
                
                self.logger.info(
                    f"State transition successful: {old_state} -> {new_state} "
                    f"(duration: {duration:.3f}s)"
                )
                return True
                
            except Exception as e:
                error_msg = f"Unexpected error during state transition {old_state} -> {new_state}: {e}"
                self.logger.error(error_msg)
                duration = time.time() - start_time
                self._record_transition(
                    old_state, 
                    new_state, 
                    success=False, 
                    error=error_msg,
                    duration=duration
                )
                with self._metrics_lock:
                    self._metrics.record_transition(
                        old_state.value, new_state.value, duration, False
                    )
                # Attempt rollback on unexpected error
                self._rollback_transition(new_state)
                return False
    
    def rollback_transition(self, from_state: RecoveryState, to_state: RecoveryState) -> bool:
        """Thread-safe attempt to rollback a failed transition."""
        with self._state_lock:
            key = (from_state, to_state)
            if key not in self._transition_validators:
                return False
            
            validator = self._transition_validators[key]
            if not validator.rollback_fn:
                return False
            
            try:
                validator.rollback_fn()
                self._current_state = from_state
                self._record_transition(to_state, from_state, success=True, error="Rollback")
                return True
            except Exception as e:
                self._record_transition(to_state, from_state, success=False, error=str(e))
                return False
    
    def reset(self) -> bool:
        """Thread-safe reset of state machine to initial state."""
        with self._state_lock:
            old_state = self._current_state
            self._current_state = RecoveryState.IDLE
            self._record_transition(old_state, RecoveryState.IDLE, success=True, error="Reset")
            self._notify_state_change(old_state, RecoveryState.IDLE)
            return True
    
    def get_current_state(self) -> str:
        """Thread-safe access to current state value."""
        with self._state_lock:
            return self._current_state.value
    
    def _get_resource_state(self) -> Optional[Dict[str, Any]]:
        """Get current state of resources."""
        if not self._resource_pool:
            return None
            
        try:
            return {
                'pool_stats': self._resource_pool.get_pool_stats(),
                'metrics': self._resource_pool.get_metrics()
            }
        except Exception as e:
            self.logger.error(f"Error getting resource state: {e}")
            return None
            
    def _get_component_state(self) -> Optional[Dict[str, Any]]:
        """Get current state of components."""
        if not self._component_coordinator:
            return None
            
        try:
            # Get active components and their states
            active_components = {}
            for component, info in self._component_coordinator.get_active_components().items():
                active_components[component] = {
                    'state': info.state.value if hasattr(info, 'state') else 'unknown',
                    'thread_failures': self._component_coordinator.get_component_thread_failures(component)
                }
            
            return {
                'active_components': active_components,
                'thread_failures': self._component_coordinator.get_thread_failures()
            }
        except Exception as e:
            self.logger.error(f"Error getting component state: {e}")
            return None
            
    def get_state_history(self) -> List[Dict]:
        """Thread-safe access to formatted state transition history with enhanced context."""
        with self._history_lock:
            return [
                {
                    'timestamp': event.timestamp,
                    'from_state': event.from_state.value,
                    'to_state': event.to_state.value,
                    'success': event.success,
                    'error': event.error,
                    'duration': event.duration,
                    'resource_state': event.resource_state,
                    'component_state': event.component_state
                }
                for event in self._history
            ]
            
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for state transitions."""
        with self._metrics_lock:
            return self._metrics.get_stats()
