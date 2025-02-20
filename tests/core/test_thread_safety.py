#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestThreadSafety",
    "type": "Test Suite",
    "description": "Core test suite for verifying thread safety features, including state transitions, cleanup dependencies, and error handling",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TTS[TestThreadSafety] --> SM[StateMachine]
                TTS --> CC[CleanupCoordinator]
                TTS --> MC[MonitoringCoordinator]
                TTS --> CT[ComponentTest]
                SM --> ST[StateTransition]
                CC --> CD[CleanupDependency]
                MC --> TM[ThreadMonitor]
                MC --> EC[ErrorContext]
        ```",
        "dependencies": {
            "StateMachine": "Thread-safe state management",
            "CleanupCoordinator": "Resource cleanup coordination",
            "MonitoringCoordinator": "System monitoring",
            "ComponentTest": "Base test functionality",
            "StateTransition": "State validation",
            "CleanupDependency": "Dependency management",
            "ThreadMonitor": "Thread status tracking",
            "ErrorContext": "Error chain preservation"
        }
    },
    "notes": [
        "Tests state transition validation and concurrency",
        "Verifies cleanup dependency management",
        "Tests thread failure detection and recovery",
        "Validates error context preservation",
        "Ensures resource cleanup coordination",
        "Tests concurrent state management"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_thread_safety.py",
            "python -m pytest tests/core/test_thread_safety.py -k test_concurrent_state_transitions"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest with threading support",
            "asyncio",
            "concurrent.futures"
        ],
        "system": {
            "memory": "2GB minimum",
            "cpu": "Multiple cores for concurrency tests"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "High thread count during concurrent tests",
            "Memory spikes during thread creation",
            "CPU intensive during parallel execution",
            "Proper cleanup of threads and resources"
        ]
    }
}
"""
import threading
import time
import pytest
import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from audio_transcriber.state_machine import StateMachine
from audio_transcriber.cleanup_coordinator import CleanupCoordinator
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import ComponentTest

class TestThreadSafety(ComponentTest):
    """Test suite for thread safety functionality.
    
    This test class verifies the thread safety mechanisms of the system,
    focusing on state management and cleanup coordination.
    
    Key Features Tested:
        - State transition validation
        - Concurrent state management
        - Cleanup dependency ordering
        - Thread failure handling
        - Error context preservation
    
    Attributes:
        coordinator (MonitoringCoordinator): System monitoring
        state_machine (StateMachine): Thread-safe state management
        cleanup_coordinator (CleanupCoordinator): Resource cleanup
    
    Example:
        class TestCustomThreading(TestThreadSafety):
            def test_custom_state(self):
                with ThreadPoolExecutor() as executor:
                    futures = [
                        executor.submit(self.state_machine.transition_to, 'CUSTOM')
                        for _ in range(10)
                    ]
                    concurrent.futures.wait(futures)
    """

    def setUp(self):
        """Set up test fixtures before each test method."""
        super().setUp()
        # Create and set new event loop for each test
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)
        
        self.coordinator = MonitoringCoordinator()
        self.state_machine = StateMachine(self.coordinator)
        self.cleanup_coordinator = CleanupCoordinator(self.coordinator)
        
        # Set shorter timeouts for tests
        self.test_timeout = 5.0  # 5 seconds max for test operations

    def tearDown(self):
        """Clean up test fixtures after each test method."""
        try:
            # Request shutdown first to prevent new operations
            self.coordinator.request_shutdown()
            
            # Then attempt cleanup with a short timeout
            try:
                self.cleanup_coordinator.cleanup()
            except Exception as e:
                self.logger.warning(f"Cleanup during teardown failed: {e}")
        finally:
            # Clean up event loop
            try:
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                self.loop.close()
            except Exception as e:
                self.logger.warning(f"Event loop cleanup failed: {e}")
            super().tearDown()

    @pytest.mark.fast
    def test_state_transition_validation(self):
        """Test state transition validation and thread safety.
        
        Verifies that state transitions follow valid paths and maintain
        thread safety. This test:
        1. Validates allowed state transitions
        2. Verifies invalid transitions fail
        3. Ensures state consistency
        
        Test Sequence:
            1. Define valid transitions
            2. Test each transition
            3. Verify state after transition
            4. Test invalid transitions
            5. Verify failure handling
        
        Expected Results:
            - Valid transitions succeed
            - Invalid transitions fail
            - State remains consistent
            - Transitions properly logged
        
        Example Metrics:
            - transition_[from]_[to]: Success count
            - Invalid transitions detected
            - State consistency maintained
        """
        # Define test transitions
        transitions = [
            ('INIT', 'STARTING'),
            ('STARTING', 'RUNNING'),
            ('RUNNING', 'PAUSED'),
            ('PAUSED', 'RUNNING'),
            ('RUNNING', 'STOPPING'),
            ('STOPPING', 'STOPPED')
        ]
        
        # Test sequential transitions
        for from_state, to_state in transitions:
            # Set initial state
            self.state_machine.set_state(from_state)
            
            # Verify transition
            success = self.state_machine.transition_to(to_state)
            self.assertTrue(success, f"Failed to transition from {from_state} to {to_state}")
            self.assertEqual(self.state_machine.get_state(), to_state)
            
            # Log transition
            self.log_metric(f"transition_{from_state}_{to_state}", 1)
        
        # Test invalid transitions
        invalid_transitions = [
            ('RUNNING', 'INIT'),
            ('STOPPED', 'PAUSED'),
            ('INIT', 'STOPPED')
        ]
        
        for from_state, to_state in invalid_transitions:
            self.state_machine.set_state(from_state)
            success = self.state_machine.transition_to(to_state)
            self.assertFalse(success, f"Invalid transition from {from_state} to {to_state} should fail")

    @pytest.mark.fast
    def test_concurrent_state_transitions(self):
        """Test concurrent state transitions from multiple threads.
        
        Verifies that state transitions remain consistent under heavy
        concurrent load. This test:
        1. Creates multiple worker threads
        2. Executes state transition cycles
        3. Verifies thread safety
        4. Monitors for errors
        
        Test Sequence:
            1. Define transition cycle
            2. Create worker threads
            3. Execute concurrent transitions
            4. Wait for completion
            5. Verify no errors occurred
        
        Expected Results:
            - No state corruption
            - No deadlocks
            - No race conditions
            - All transitions complete
        
        Example Metrics:
            - total_transitions: Total transitions executed
            - concurrent_threads: Number of threads
            - errors: Error count (should be 0)
        """
        transition_count = 100
        thread_count = 4
        errors = []
        
        def transition_worker():
            try:
                for _ in range(transition_count):
                    # Attempt state cycle
                    self.state_machine.transition_to('STARTING')
                    self.state_machine.transition_to('RUNNING')
                    self.state_machine.transition_to('PAUSED')
                    self.state_machine.transition_to('RUNNING')
                    self.state_machine.transition_to('STOPPING')
                    self.state_machine.transition_to('STOPPED')
            except Exception as e:
                errors.append(e)
        
        # Run concurrent transitions
        threads = []
        for _ in range(thread_count):
            thread = threading.Thread(target=transition_worker)
            thread.start()
            threads.append(thread)
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Encountered errors during concurrent transitions: {errors}")
        
        # Log concurrency metrics
        self.log_metric("total_transitions", transition_count * thread_count * 6)
        self.log_metric("concurrent_threads", thread_count)
        self.log_metric("errors", len(errors))

    @pytest.mark.timeout(10)  # 10 second total test timeout
    @pytest.mark.fast
    def test_cleanup_dependencies(self):
        """Test cleanup step dependencies and validation.
        
        Verifies that cleanup steps execute in the correct order
        respecting their dependencies. This test:
        1. Defines cleanup steps with dependencies
        2. Verifies execution order
        3. Validates dependency constraints
        
        Test Sequence:
            1. Define cleanup steps
            2. Register with dependencies
            3. Execute cleanup sequence
            4. Verify execution order
            5. Check dependency rules
        
        Expected Results:
            - All steps execute
            - Dependencies respected
            - Proper execution order
            - Performance logged
        
        Example Metrics:
            - cleanup_steps: Number of steps
            - execution_time: Total cleanup time
            - dependency_violations: Should be 0
        """
        # Define cleanup steps with dependencies
        steps = [
            {'id': 'stop_capture', 'dependencies': []},
            {'id': 'flush_buffers', 'dependencies': ['stop_capture']},
            {'id': 'close_files', 'dependencies': ['flush_buffers']},
            {'id': 'release_resources', 'dependencies': ['close_files']}
        ]
        
        try:
            # Register cleanup steps
            for step in steps:
                self.logger.info(f"Registering cleanup step: {step['id']}")
                self.cleanup_coordinator.register_step(
                    step['id'],
                    lambda: None,  # Quick no-op for testing
                    dependencies=step['dependencies']
                )
            
            # Execute cleanup with strict timeout
            try:
                success = self.loop.run_until_complete(
                    asyncio.wait_for(
                        self.cleanup_coordinator.execute_cleanup(),
                        timeout=self.test_timeout
                    )
                )
                self.assertTrue(success, "Cleanup execution failed")
            except asyncio.TimeoutError:
                self.logger.error("Cleanup execution timed out")
                # Get current status for debugging
                status = self.cleanup_coordinator.get_cleanup_status()
                self.logger.error(
                    f"Cleanup status at timeout: phase={status['phase']}, "
                    f"completed={status['completed_steps']}, "
                    f"failed={status['failed_steps']}, "
                    f"pending={status['pending_steps']}"
                )
                pytest.fail("Cleanup execution timed out - possible deadlock")
            
            # Get execution order atomically
            execution_order = self.cleanup_coordinator.get_execution_order()
            
            # Verify all steps were executed
            self.assertEqual(
                len(execution_order),
                len(steps),
                "Not all steps were executed"
            )
            
            # Verify dependencies were respected
            for step in steps:
                step_index = execution_order.index(step['id'])
                for dep in step['dependencies']:
                    dep_index = execution_order.index(dep)
                    self.assertLess(
                        dep_index,
                        step_index,
                        f"Dependency {dep} executed after dependent step {step['id']}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Test failed: {e}")
            raise
        
        # Log cleanup metrics
        self.log_metric("cleanup_steps", len(steps))
        self.log_metric("execution_time", self.cleanup_coordinator.get_execution_time())

    @pytest.mark.fast
    def test_thread_failure_detection(self):
        """Test thread failure detection and handling.
        
        Verifies the system's ability to detect and handle thread
        failures and hangs. This test:
        1. Simulates thread failures
        2. Tests hang detection
        3. Verifies failure handling
        
        Test Sequence:
            1. Create failing thread
            2. Verify failure detection
            3. Create hanging thread
            4. Verify timeout detection
            5. Check thread status
        
        Expected Results:
            - Failures detected
            - Hangs identified
            - Proper status tracking
            - Metrics recorded
        
        Example Metrics:
            - failed_threads: Number of failed threads
            - hung_threads: Number of hung threads
            - active_threads: Number of active threads
        """
        def failing_thread():
            raise RuntimeError("Simulated thread failure")
        
        def slow_thread():
            time.sleep(10.0)  # Simulate hanging thread
        
        # Test failure detection
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Start failing thread
            future = executor.submit(failing_thread)
            
            # Wait for failure detection
            time.sleep(0.5)
            
            # Verify failure was detected
            thread_status = self.coordinator.get_thread_status()
            self.assertIn('failed', thread_status)
            self.assertGreater(len(thread_status['failed']), 0)
        
        # Test timeout detection
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Start slow thread
            future = executor.submit(slow_thread)
            
            # Wait for timeout detection
            time.sleep(2.0)
            
            # Verify timeout was detected
            thread_status = self.coordinator.get_thread_status()
            self.assertIn('hung', thread_status)
            self.assertGreater(len(thread_status['hung']), 0)
        
        # Log thread monitoring metrics
        status = self.coordinator.get_thread_status()
        self.log_metric("failed_threads", len(status['failed']))
        self.log_metric("hung_threads", len(status['hung']))
        self.log_metric("active_threads", len(status['active']))

    @pytest.mark.fast
    def test_lock_ordering(self):
        """Test lock ordering and hierarchy validation.
        
        Verifies that locks are acquired and released in the correct order
        to prevent deadlocks. This test:
        1. Validates lock hierarchy
        2. Tests acquisition order
        3. Verifies release order
        
        Test Sequence:
            1. Define lock hierarchy
            2. Test nested acquisition
            3. Test reverse acquisition
            4. Verify cleanup
        
        Expected Results:
            - Proper lock ordering maintained
            - No deadlocks occur
            - All locks released
            - Metrics recorded
        
        Example Metrics:
            - lock_acquisitions: Number of lock acquisitions
            - lock_releases: Number of lock releases
            - lock_timeouts: Number of timeouts (should be 0)
        """
        # Define lock hierarchy (state -> metrics -> perf -> component -> update)
        locks = {
            'state': threading.Lock(),
            'metrics': threading.Lock(),
            'perf': threading.Lock(),
            'component': threading.Lock(),
            'update': threading.Lock()
        }
        
        lock_order = ['state', 'metrics', 'perf', 'component', 'update']
        acquisitions = []
        releases = []
        
        def acquire_locks(order):
            """Acquire locks in specified order."""
            for lock_name in order:
                if locks[lock_name].acquire(timeout=1.0):
                    acquisitions.append(lock_name)
                else:
                    raise TimeoutError(f"Failed to acquire {lock_name} lock")
        
        def release_locks():
            """Release locks in reverse order."""
            while acquisitions:
                lock_name = acquisitions.pop()
                locks[lock_name].release()
                releases.append(lock_name)
        
        try:
            # Test proper lock ordering
            acquire_locks(lock_order)
            self.assertEqual(acquisitions, lock_order)
            release_locks()
            self.assertEqual(releases, lock_order[::-1])
            
            # Test reverse order (should fail)
            with self.assertRaises(TimeoutError):
                acquire_locks(lock_order[::-1])
            
            # Test partial acquisition
            partial_order = lock_order[:3]
            acquire_locks(partial_order)
            self.assertEqual(acquisitions, partial_order)
            release_locks()
            self.assertEqual(releases, partial_order[::-1])
            
        finally:
            # Emergency cleanup
            for lock_name in acquisitions[::-1]:
                locks[lock_name].release()
        
        # Log lock metrics
        self.log_metric("lock_acquisitions", len(acquisitions))
        self.log_metric("lock_releases", len(releases))
        self.log_metric("lock_timeouts", 1)  # Expected timeout from reverse order test

    @pytest.mark.fast
    def test_resource_coordination(self):
        """Test concurrent resource coordination and component interaction.
        
        Verifies that resources are properly coordinated between components
        under concurrent load. This test:
        1. Tests resource allocation
        2. Verifies component coordination
        3. Tests state transitions
        
        Test Sequence:
            1. Initialize components
            2. Allocate resources
            3. Test concurrent access
            4. Verify cleanup
        
        Expected Results:
            - Resources properly allocated
            - Components coordinated
            - No resource leaks
            - Metrics recorded
        
        Example Metrics:
            - resource_allocations: Number of allocations
            - component_transitions: Number of transitions
            - coordination_failures: Number of failures
        """
        # Initialize test components
        components = {
            'audio': Mock(allocate=Mock(return_value=True), release=Mock(return_value=True)),
            'buffer': Mock(allocate=Mock(return_value=True), release=Mock(return_value=True)),
            'storage': Mock(allocate=Mock(return_value=True), release=Mock(return_value=True))
        }
        
        # Track metrics
        metrics = {
            'allocations': 0,
            'releases': 0,
            'failures': 0
        }
        metrics_lock = threading.Lock()
        
        def component_worker(component_name):
            try:
                # Allocate resources
                component = components[component_name]
                if component.allocate():
                    with metrics_lock:
                        metrics['allocations'] += 1
                    
                    # Simulate work
                    time.sleep(0.001)
                    
                    # Release resources
                    if component.release():
                        with metrics_lock:
                            metrics['releases'] += 1
                else:
                    with metrics_lock:
                        metrics['failures'] += 1
            except Exception as e:
                self.coordinator.record_error(e)
        
        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=len(components)) as executor:
            futures = []
            for _ in range(100):  # 100 operations per component
                for component_name in components:
                    futures.append(executor.submit(component_worker, component_name))
            
            # Wait for completion
            for future in futures:
                future.result()
        
        # Verify results
        self.assertEqual(metrics['failures'], 0)
        self.assertEqual(metrics['allocations'], metrics['releases'])
        
        # Log coordination metrics
        self.log_metric("resource_allocations", metrics['allocations'])
        self.log_metric("resource_releases", metrics['releases'])
        self.log_metric("coordination_failures", metrics['failures'])

    @pytest.mark.fast
    def test_deadlock_prevention(self):
        """Test deadlock prevention mechanisms.
        
        Verifies that the system properly prevents and detects potential
        deadlocks. This test:
        1. Tests timeout mechanisms
        2. Verifies lock release
        3. Tests resource cleanup
        
        Test Sequence:
            1. Create potential deadlock
            2. Verify timeout detection
            3. Test cleanup triggers
            4. Verify recovery
        
        Expected Results:
            - Deadlocks prevented
            - Timeouts trigger
            - Resources cleaned up
            - Metrics recorded
        
        Example Metrics:
            - timeout_triggers: Number of timeouts
            - cleanup_triggers: Number of cleanups
            - recovery_time: Time to recover
        """
        # Track metrics
        metrics = {
            'timeouts': 0,
            'cleanups': 0,
            'start_time': None,
            'end_time': None
        }
        
        def deadlock_worker(lock1, lock2):
            try:
                # Try to acquire first lock
                if not lock1.acquire(timeout=1.0):
                    with metrics_lock:
                        metrics['timeouts'] += 1
                    return
                
                try:
                    # Simulate work
                    time.sleep(0.1)
                    
                    # Try to acquire second lock
                    if not lock2.acquire(timeout=1.0):
                        with metrics_lock:
                            metrics['timeouts'] += 1
                        return
                    
                    try:
                        # Critical section
                        time.sleep(0.1)
                    finally:
                        lock2.release()
                finally:
                    lock1.release()
                    
            except Exception as e:
                self.coordinator.record_error(e)
                with metrics_lock:
                    metrics['cleanups'] += 1
        
        # Create locks
        lock_a = threading.Lock()
        lock_b = threading.Lock()
        metrics_lock = threading.Lock()
        
        # Start timing
        metrics['start_time'] = time.time()
        
        # Create potential deadlock situation
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Thread 1: tries to acquire A then B
            # Thread 2: tries to acquire B then A
            future1 = executor.submit(deadlock_worker, lock_a, lock_b)
            future2 = executor.submit(deadlock_worker, lock_b, lock_a)
            
            # Wait for completion
            future1.result()
            future2.result()
        
        # End timing
        metrics['end_time'] = time.time()
        
        # Verify results
        self.assertGreater(metrics['timeouts'], 0)  # Should have some timeouts
        self.assertEqual(metrics['cleanups'], 0)  # Should have no cleanup triggers
        
        # Log prevention metrics
        self.log_metric("timeout_triggers", metrics['timeouts'])
        self.log_metric("cleanup_triggers", metrics['cleanups'])
        self.log_metric("recovery_time", metrics['end_time'] - metrics['start_time'])

    @pytest.mark.fast
    def test_error_context_verification(self):
        """Test error context preservation and verification.
        
        Verifies that error context and chain information is properly
        preserved and tracked. This test:
        1. Creates error chain
        2. Verifies context capture
        3. Validates error details
        
        Test Sequence:
            1. Generate error chain
            2. Capture error context
            3. Verify chain length
            4. Check context fields
            5. Validate root cause
        
        Expected Results:
            - Error chain preserved
            - Context fields present
            - Root cause identified
            - Proper error typing
        
        Example Metrics:
            - error_chain_length: Length of error chain
            - context_fields: Number of context fields
            - error_types: Types in chain
        """
        # Create test error chain
        try:
            try:
                try:
                    raise ValueError("Root cause")
                except ValueError as e:
                    raise RuntimeError("Middle error") from e
            except RuntimeError as e:
                raise Exception("Top level error") from e
        except Exception as e:
            error_context = self.coordinator.capture_error_context(e)
        
        # Verify error chain
        self.assertIn('chain', error_context)
        self.assertEqual(len(error_context['chain']), 3)
        
        # Verify context information
        self.assertIn('thread_id', error_context)
        self.assertIn('timestamp', error_context)
        self.assertIn('state', error_context)
        
        # Verify root cause is preserved
        root_cause = error_context['chain'][-1]
        self.assertIn('ValueError', root_cause['type'])
        self.assertIn('Root cause', root_cause['message'])
        
        # Log error context metrics
        self.log_metric("error_chain_length", len(error_context['chain']))
        self.log_metric("context_fields", len(error_context))

if __name__ == '__main__':
    unittest.main()
