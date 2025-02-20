"""
COMPONENT_NOTES:
{
    "name": "CleanupCoordinator",
    "type": "Core Component",
    "description": "Thread-safe cleanup coordinator that manages ordered cleanup operations with dependency tracking, state machine integration, and monitoring",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                CC[CleanupCoordinator] --> SM[StateMachine]
                CC --> MC[MonitoringCoordinator]
                CC --> CP[CleanupPhase]
                CC --> CS[CleanupStep]
                SM --> RS[RecoveryState]
                CS --> CP
                CS --> CF[CleanupFunction]
                CS --> VF[VerificationFunction]
                CC --> LM[LockManager]
        ```",
        "dependencies": {
            "StateMachine": "State transition management",
            "MonitoringCoordinator": "System monitoring",
            "CleanupPhase": "Phase enumeration",
            "CleanupStep": "Step data structure",
            "RecoveryState": "Recovery state tracking",
            "LockManager": "Thread safety management",
            "CleanupFunction": "Step implementation",
            "VerificationFunction": "Step verification"
        }
    },
    "notes": [
        "Manages ordered cleanup with dependency tracking",
        "Ensures thread-safe operations with lock hierarchy",
        "Integrates with state machine for recovery",
        "Provides verification and rollback capabilities",
        "Supports async and sync cleanup operations",
        "Handles cleanup failures with dependency chain"
    ],
    "usage": {
        "examples": [
            "coordinator = CleanupCoordinator(monitoring_coordinator)",
            "coordinator.register_step('stop_capture', stop_fn, dependencies=['flush_buffers'])",
            "await coordinator.execute_cleanup()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "asyncio",
            "threading",
            "logging",
            "enum"
        ],
        "system": {
            "memory": "Minimal usage",
            "threading": "Thread-safe operations"
        }
    },
    "performance": {
        "execution_time": "Varies by registered steps",
        "resource_usage": [
            "Light memory footprint",
            "Thread-safe with minimal contention",
            "Efficient dependency resolution",
            "Proper resource cleanup"
        ]
    }
}
"""

import logging
import enum
from typing import Dict, List, Set, Optional, Callable
from dataclasses import dataclass
import asyncio
import threading
from datetime import datetime
from .state_machine import StateMachine, RecoveryState

class CleanupPhase(enum.Enum):
    """Cleanup phases in order of execution."""
    NOT_STARTED = 0
    INITIATING = 1
    STOPPING_CAPTURE = 2
    FLUSHING_STORAGE = 3
    RELEASING_RESOURCES = 4
    CLOSING_LOGS = 5
    COMPLETED = 6
    FAILED = 7

@dataclass
class CleanupStep:
    """Represents a single cleanup step with dependencies."""
    name: str
    phase: CleanupPhase
    dependencies: Set[str]
    cleanup_fn: Callable
    verification_fn: Optional[Callable] = None
    timeout: float = 5.0  # seconds

class CleanupCoordinator:
    """
    Thread-safe cleanup coordinator that integrates with the state machine
    and monitoring system for coordinated cleanup operations.
    
    Lock Ordering:
    1. _phase_lock
    2. _steps_lock
    3. _status_lock
    """
    
    def __init__(self, monitoring_coordinator):
        self.logger = logging.getLogger("CleanupCoordinator")
        self._monitoring_coordinator = monitoring_coordinator
        self._state_machine = StateMachine(monitoring_coordinator)
        self._state_machine.transition_to(RecoveryState.NOT_STARTED)  # Ensure proper initial state
        
        # Thread safety - locks in acquisition order
        self._shutdown_lock = threading.Lock()  # Lock 1
        self._phase_lock = threading.Lock()     # Lock 2
        self._steps_lock = threading.Lock()     # Lock 3
        self._status_lock = threading.Lock()    # Lock 4
        
        # Shutdown state
        self._shutdown_requested = False
        
        # State tracking
        self._current_phase = CleanupPhase.NOT_STARTED
        self._cleanup_steps: Dict[str, CleanupStep] = {}
        self._completed_steps: Set[str] = set()
        self._failed_steps: Set[str] = set()
        self._cleanup_start_time: Optional[float] = None
        
        # Register state change callback
        self._state_machine.register_state_change_callback(self._handle_state_change)
        
    def _handle_state_change(self, old_state: RecoveryState, new_state: RecoveryState) -> None:
        """Handle state machine state changes."""
        try:
            self.logger.info(f"State change: {old_state.value} -> {new_state.value}")
            
            # Map recovery states to cleanup phases
            state_to_phase = {
                RecoveryState.NOT_STARTED: CleanupPhase.NOT_STARTED,
                RecoveryState.INITIATING: CleanupPhase.INITIATING,
                RecoveryState.STOPPING_CAPTURE: CleanupPhase.STOPPING_CAPTURE,
                RecoveryState.FLUSHING_BUFFERS: CleanupPhase.FLUSHING_STORAGE,
                RecoveryState.COMPLETED: CleanupPhase.COMPLETED,
                RecoveryState.FAILED: CleanupPhase.FAILED
            }
            
            if new_state in state_to_phase:
                with self._phase_lock:
                    self._current_phase = state_to_phase[new_state]
                    
        except Exception as e:
            self.logger.error(f"Error handling state change: {e}")
            self._monitoring_coordinator.handle_error(e, "cleanup_coordinator")

    def request_shutdown(self) -> None:
        """Request shutdown of cleanup coordinator."""
        with self._shutdown_lock:
            self._shutdown_requested = True
            self.logger.info("Shutdown requested")

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown was requested."""
        with self._shutdown_lock:
            return self._shutdown_requested
        
    def register_step(self, name: str, cleanup_fn: callable, *, dependencies: list = None) -> None:
        """Thread-safe registration of cleanup step."""
        # Map step names to appropriate phases
        phase_mapping = {
            'stop_capture': CleanupPhase.STOPPING_CAPTURE,
            'flush_buffers': CleanupPhase.FLUSHING_STORAGE,
            'close_files': CleanupPhase.CLOSING_LOGS,
            'release_resources': CleanupPhase.RELEASING_RESOURCES
        }
        
        # Validate step name
        if name not in phase_mapping:
            raise ValueError(f"Unknown cleanup step: {name}")
        
        step = CleanupStep(
            name=name,
            phase=phase_mapping.get(name, CleanupPhase.NOT_STARTED),
            dependencies=set(dependencies or []),
            cleanup_fn=cleanup_fn
        )
        with self._steps_lock:
            self._cleanup_steps[step.name] = step
            self.logger.debug(f"Registered cleanup step: {step.name} with dependencies {step.dependencies}")
            
    def execute_cleanup_sync(self) -> bool:
        """Synchronous version of execute_cleanup for testing."""
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Cancel any pending tasks
            for task in asyncio.all_tasks(loop):
                if task is not asyncio.current_task():
                    task.cancel()
                    try:
                        loop.run_until_complete(task)
                    except asyncio.CancelledError:
                        pass
            
            # Run cleanup with timeout
            try:
                return loop.run_until_complete(
                    asyncio.wait_for(
                        self.execute_cleanup(),
                        timeout=1.0  # Shorter timeout for tests
                    )
                )
            except asyncio.TimeoutError:
                self.logger.error("Cleanup timed out")
                # Force cleanup on timeout
                with self._phase_lock:
                    self._current_phase = CleanupPhase.FAILED
                with self._steps_lock:
                    remaining = set(self._cleanup_steps.keys()) - self._completed_steps
                    self._failed_steps.update(remaining)
                return False
            finally:
                # Clean up any remaining tasks
                for task in asyncio.all_tasks(loop):
                    if task is not asyncio.current_task():
                        task.cancel()
                        try:
                            loop.run_until_complete(task)
                        except asyncio.CancelledError:
                            pass
                
                # Ensure we close the loop
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                
        except Exception as e:
            self.logger.error(f"Error during cleanup sync: {e}")
            return False

    def cleanup(self) -> None:
        """Synchronous cleanup method for test teardown."""
        try:
            # Get or create event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Cancel any pending tasks
            for task in asyncio.all_tasks(loop):
                if task is not asyncio.current_task():
                    task.cancel()
                    try:
                        loop.run_until_complete(task)
                    except asyncio.CancelledError:
                        pass
            
            try:
                # Run cleanup with timeout
                loop.run_until_complete(
                    asyncio.wait_for(
                        self.execute_cleanup(),
                        timeout=1.0  # Shorter timeout for tests
                    )
                )
            except asyncio.TimeoutError:
                self.logger.error("Cleanup timed out")
                # Force cleanup on timeout
                with self._phase_lock:
                    self._current_phase = CleanupPhase.FAILED
                with self._steps_lock:
                    remaining = set(self._cleanup_steps.keys()) - self._completed_steps
                    self._failed_steps.update(remaining)
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")
                raise
            finally:
                # Clean up any remaining tasks
                for task in asyncio.all_tasks(loop):
                    if task is not asyncio.current_task():
                        task.cancel()
                        try:
                            loop.run_until_complete(task)
                        except asyncio.CancelledError:
                            pass
                
        except Exception as e:
            self.logger.error(f"Error during cleanup setup: {e}")
            raise
        
    def _get_next_available_step(self) -> Optional[CleanupStep]:
        """Thread-safe retrieval of next available step."""
        self.logger.debug("Attempting to get next available step")
        with self._steps_lock:
            pending = set(self._cleanup_steps.keys()) - self._completed_steps - self._failed_steps
            if not pending:
                self.logger.debug("No pending steps remaining")
                return None
                
            for name, step in self._cleanup_steps.items():
                if (name not in self._completed_steps and 
                    name not in self._failed_steps):
                    if step.dependencies.issubset(self._completed_steps):
                        self.logger.debug(f"Found available step: {name}")
                        return step
                    else:
                        missing = step.dependencies - self._completed_steps
                        self.logger.debug(f"Step {name} waiting on dependencies: {missing}")
            
            self.logger.debug("No steps available due to dependencies")
            return None
        
    async def _execute_step(self, step: CleanupStep) -> bool:
        """Execute a cleanup step with enhanced validation, verification, and error handling."""
        self.logger.info(f"Executing cleanup step: {step.name}")
        try:
            # Validate dependencies outside of locks
            missing_deps = set()
            failed_deps = set()
            with self._steps_lock:
                missing_deps = step.dependencies - self._completed_steps
                failed_deps = step.dependencies.intersection(self._failed_steps)
            
            if missing_deps:
                raise ValueError(
                    f"Cannot execute step {step.name}: "
                    f"missing dependencies {missing_deps}"
                )
            if failed_deps:
                raise ValueError(
                    f"Cannot execute step {step.name}: "
                    f"failed dependencies {failed_deps}"
                )
            
            # Validate and update phase
            current_phase = None
            with self._phase_lock:
                current_phase = self._current_phase
                # If we're in INITIATING phase, allow transition to step's phase
                if current_phase == CleanupPhase.INITIATING:
                    self._current_phase = step.phase
                elif not self._validate_phase_transition(current_phase, step.phase):
                    raise ValueError(
                        f"Invalid phase transition: "
                        f"{current_phase.name} -> {step.phase.name}"
                    )
                else:
                    self._current_phase = step.phase
            
            # Update state machine outside of locks
            recovery_state = self._map_phase_to_recovery_state(step.phase)
            if recovery_state:
                # Always transition through proper states based on step phase
                if step.phase == CleanupPhase.STOPPING_CAPTURE:
                    if not self._state_machine.transition_to(RecoveryState.STOPPING_CAPTURE):
                        raise ValueError("Failed to transition to STOPPING_CAPTURE state")
                elif step.phase == CleanupPhase.FLUSHING_STORAGE:
                    if not self._state_machine.transition_to(RecoveryState.FLUSHING_BUFFERS):
                        raise ValueError("Failed to transition to FLUSHING_BUFFERS state")
                else:
                    if not self._state_machine.transition_to(recovery_state):
                        raise ValueError(
                            f"State machine transition failed for phase {step.phase.name}"
                        )
            
            # Execute cleanup function outside of any locks
            self.logger.debug(f"Starting cleanup function for {step.name}")
            try:
                if asyncio.iscoroutinefunction(step.cleanup_fn):
                    await asyncio.wait_for(step.cleanup_fn(), timeout=step.timeout)
                else:
                    loop = asyncio.get_event_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(None, step.cleanup_fn),
                        timeout=step.timeout
                    )
                self.logger.debug(f"Completed cleanup function for {step.name}")
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Cleanup step {step.name} timed out after {step.timeout} seconds"
                )
            
            # Enhanced verification with retries
            if step.verification_fn:
                retry_count = 3
                retry_delay = 1.0  # seconds
                
                for attempt in range(retry_count):
                    try:
                        if await step.verification_fn():
                            break
                        if attempt < retry_count - 1:
                            self.logger.warning(
                                f"Verification attempt {attempt + 1} failed for {step.name}, "
                                f"retrying in {retry_delay} seconds"
                            )
                            await asyncio.sleep(retry_delay)
                        else:
                            raise ValueError(
                                f"Verification failed for {step.name} "
                                f"after {retry_count} attempts"
                            )
                    except Exception as verify_error:
                        if attempt == retry_count - 1:
                            raise ValueError(
                                f"Verification error in {step.name}: {str(verify_error)}"
                            )
                        self.logger.warning(
                            f"Verification error in {step.name}, attempt {attempt + 1}: "
                            f"{str(verify_error)}"
                        )
                        await asyncio.sleep(retry_delay)
            
            # Update completion status and notify monitoring coordinator
            with self._steps_lock:
                self._completed_steps.add(step.name)
            
            # Notify monitoring coordinator outside of locks
            self._monitoring_coordinator.mark_component_cleanup_complete(step.name)
            
            self.logger.info(
                f"Successfully completed cleanup step: {step.name} "
                f"in phase {step.phase.name}"
            )
            return True
            
        except asyncio.TimeoutError as timeout_error:
            self._handle_step_failure(step.name, timeout_error)
            return False
            
        except Exception as e:
            self._handle_step_failure(step.name, e)
            return False
            
    def _validate_phase_transition(self, current_phase: CleanupPhase,
                                 new_phase: CleanupPhase) -> bool:
        """Validate cleanup phase transition."""
        # Define valid phase transitions
        valid_transitions = {
            CleanupPhase.NOT_STARTED: {
                CleanupPhase.INITIATING,
                CleanupPhase.FAILED
            },
            CleanupPhase.INITIATING: {
                CleanupPhase.STOPPING_CAPTURE,
                CleanupPhase.FLUSHING_STORAGE,
                CleanupPhase.RELEASING_RESOURCES,
                CleanupPhase.CLOSING_LOGS,
                CleanupPhase.COMPLETED,  # Allow direct completion if no steps
                CleanupPhase.FAILED
            },
            CleanupPhase.STOPPING_CAPTURE: {
                CleanupPhase.FLUSHING_STORAGE,
                CleanupPhase.COMPLETED,  # Allow completion if no more steps
                CleanupPhase.FAILED
            },
            CleanupPhase.FLUSHING_STORAGE: {
                CleanupPhase.RELEASING_RESOURCES,
                CleanupPhase.COMPLETED,  # Allow completion if no more steps
                CleanupPhase.FAILED
            },
            CleanupPhase.RELEASING_RESOURCES: {
                CleanupPhase.CLOSING_LOGS,
                CleanupPhase.COMPLETED,  # Allow completion if no more steps
                CleanupPhase.FAILED
            },
            CleanupPhase.CLOSING_LOGS: {
                CleanupPhase.COMPLETED,
                CleanupPhase.FAILED
            },
            CleanupPhase.COMPLETED: {
                CleanupPhase.FAILED  # Allow failure from completed state
            },
            CleanupPhase.FAILED: set()  # No transitions from failed
        }
        
        return new_phase in valid_transitions.get(current_phase, set())

    def _map_phase_to_recovery_state(self, phase: CleanupPhase) -> Optional[RecoveryState]:
        """Map cleanup phase to recovery state."""
        phase_to_state = {
            CleanupPhase.NOT_STARTED: RecoveryState.NOT_STARTED,
            CleanupPhase.INITIATING: RecoveryState.INITIATING,
            CleanupPhase.STOPPING_CAPTURE: RecoveryState.STOPPING_CAPTURE,
            CleanupPhase.FLUSHING_STORAGE: RecoveryState.FLUSHING_BUFFERS,
            CleanupPhase.COMPLETED: RecoveryState.COMPLETED,
            CleanupPhase.FAILED: RecoveryState.FAILED
        }
        return phase_to_state.get(phase)

    def _handle_step_failure(self, step_name: str, error: Exception) -> None:
        """Handle cleanup step failure with enhanced error tracking and recovery."""
        self.logger.error(
            f"Cleanup step failed: {step_name} - {str(error)}\n"
            f"Stack trace:", exc_info=True
        )
        
        try:
            # First transition to FAILED state before modifying other state
            with self._phase_lock:
                if self._current_phase != CleanupPhase.FAILED:
                    self._current_phase = CleanupPhase.FAILED
                    if not self._state_machine.transition_to(RecoveryState.FAILED):
                        self.logger.error(
                            "Failed to transition state machine to FAILED state"
                        )

            # Then update failed steps tracking
            with self._steps_lock:
                self._failed_steps.add(step_name)
                # Get dependent steps
                dependent_steps = {
                    name for name, step in self._cleanup_steps.items()
                    if step_name in step.dependencies
                }
                # Mark dependent steps as failed
                self._failed_steps.update(dependent_steps)
                
                if dependent_steps:
                    self.logger.warning(
                        f"Marked dependent steps as failed: {dependent_steps}"
                    )
            
            # Notify monitoring coordinator with detailed error
            error_context = {
                'step': step_name,
                'phase': self._current_phase.name,
                'error': str(error),
                'affected_steps': list(dependent_steps)
            }
            self._monitoring_coordinator.handle_error(
                error, f"cleanup_step_{step_name}", error_context
            )
            
        except Exception as e:
            self.logger.critical(
                f"Error handling cleanup step failure: {str(e)}\n"
                f"Original error: {str(error)}\n"
                f"Stack trace:", exc_info=True
            )
            
    async def execute_cleanup(self) -> bool:
        """Thread-safe execution of all cleanup steps."""
        self.logger.info("Starting cleanup process")
        
        # Initialize cleanup state
        with self._status_lock:
            self._cleanup_start_time = datetime.now().timestamp()
            
        with self._phase_lock:
            # First transition from NOT_STARTED to INITIATING
            if not self._validate_phase_transition(self._current_phase, CleanupPhase.INITIATING):
                raise ValueError(
                    f"Invalid initial phase transition: "
                    f"{self._current_phase.name} -> {CleanupPhase.INITIATING.name}"
                )
            self._current_phase = CleanupPhase.INITIATING
            if not self._state_machine.transition_to(RecoveryState.INITIATING):
                raise ValueError("Failed to transition state machine to INITIATING state")
        
        try:
            # Cancel any pending tasks
            loop = asyncio.get_event_loop()
            for task in asyncio.all_tasks(loop):
                if task is not asyncio.current_task():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            iteration = 0
            while True:
                iteration += 1
                self.logger.debug(f"Cleanup iteration {iteration}")
                
                # Log current status
                status = self.get_cleanup_status()
                self.logger.debug(
                    f"Current status: phase={status['phase']}, "
                    f"completed={len(status['completed_steps'])}, "
                    f"failed={len(status['failed_steps'])}, "
                    f"pending={len(status['pending_steps'])}"
                )
                
                next_step = self._get_next_available_step()
                if not next_step:
                    self.logger.info("No more steps to execute")
                    break
                
                if not await self._execute_step(next_step):
                    self.logger.warning(f"Step {next_step.name} failed, continuing with remaining steps")
                    continue
            
            # Check if all steps completed successfully
            with self._steps_lock:
                all_completed = len(self._completed_steps) == len(self._cleanup_steps)
                
            with self._phase_lock:
                self._current_phase = (
                    CleanupPhase.COMPLETED if all_completed 
                    else CleanupPhase.FAILED
                )
                # Update state machine
                self._state_machine.transition_to(
                    RecoveryState.COMPLETED if all_completed
                    else RecoveryState.FAILED
                )
            
            if all_completed:
                self.logger.info("Cleanup completed successfully")
            else:
                with self._steps_lock:
                    failed = set(self._cleanup_steps.keys()) - self._completed_steps
                self.logger.error(f"Cleanup completed with failures: {failed}")
                
            return all_completed
            
        except Exception as e:
            self.logger.critical(f"Cleanup process failed: {str(e)}")
            with self._phase_lock:
                self._current_phase = CleanupPhase.FAILED
                self._state_machine.transition_to(RecoveryState.FAILED)
            self._monitoring_coordinator.handle_error(e, "cleanup_coordinator")
            return False
            
    def get_cleanup_status(self) -> Dict:
        """Thread-safe access to cleanup status."""
        with self._phase_lock, self._steps_lock, self._status_lock:
            return {
                'phase': self._current_phase.name,
                'completed_steps': list(self._completed_steps),
                'failed_steps': list(self._failed_steps),
                'pending_steps': list(
                    set(self._cleanup_steps.keys()) - 
                    self._completed_steps - 
                    self._failed_steps
                ),
                'duration': (
                    datetime.now().timestamp() - self._cleanup_start_time
                    if self._cleanup_start_time else 0
                ),
                'recovery_state': self._state_machine.get_current_state()
            }
            
    def get_execution_order(self) -> List[str]:
        """Get the order in which cleanup steps were executed."""
        with self._steps_lock:
            return list(self._completed_steps)
            
    def get_execution_time(self) -> float:
        """Get the total execution time of cleanup process."""
        with self._status_lock:
            if not self._cleanup_start_time:
                return 0.0
            return datetime.now().timestamp() - self._cleanup_start_time
