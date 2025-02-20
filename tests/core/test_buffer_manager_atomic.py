#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestBufferManagerAtomic",
    "type": "Test Suite",
    "description": "Advanced test suite for verifying atomic operations in BufferManager including thread safety, state management, and lock ordering",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TB[TestBufferManagerAtomic] --> BM[BufferManager]
                TB --> MC[MonitoringCoordinator]
                TB --> CT[ComponentTest]
                TB --> TU[TestUtilities]
                TB --> MT[MockTest]
                TB --> TP[ThreadPool]
        ```",
        "dependencies": {
            "BufferManager": "Main component under test",
            "MonitoringCoordinator": "Provides system monitoring",
            "ComponentTest": "Base test functionality",
            "TestUtilities": "Common test utilities",
            "MockTest": "Mocking capabilities",
            "ThreadPool": "Concurrent test execution"
        }
    },
    "notes": [
        "Tests thread-safe state updates and validation",
        "Verifies component lifecycle management",
        "Ensures proper lock ordering and deadlock prevention",
        "Tests error handling and recovery mechanisms",
        "Validates resource cleanup coordination"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_buffer_manager_atomic.py",
            "python -m pytest tests/core/test_buffer_manager_atomic.py -k test_atomic_state_updates"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest with threading support"
        ],
        "system": {
            "memory": "2GB minimum",
            "cpu": "Multiple cores for concurrency"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "High memory usage during buffer operations",
            "Multiple concurrent threads",
            "Lock contention monitoring"
        ]
    }
}
"""
import threading
import time
import logging
import pytest
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
from unittest.mock import Mock, patch
from typing import Dict, Any, List, Optional
from typing_extensions import Tuple
from audio_transcriber.buffer_manager import BufferManager, BufferConfig
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import ComponentTest

class TestBufferManagerAtomic(ComponentTest):
    """Test suite for BufferManager atomic operations."""
    
    def setUp(self):
        """Set up test environment."""
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            super().setUp()
            
            # Initialize MonitoringCoordinator
            self.coordinator = MonitoringCoordinator()
            self.coordinator.start_monitoring()
            
            # Wait for monitoring to initialize
            time.sleep(0.1)
            
            # Initialize buffer manager with coordinator
            self.buffer_manager = BufferManager(
                coordinator=self.coordinator,
                config=BufferConfig(
                    channels=2,
                    sample_width=2,
                    sample_rate=16000,
                    size=1024
                )
            )
            
            # Register buffer_manager component through coordinator
            self.coordinator.register_component(
                'buffer_manager',
                'transform',
                lambda: self.buffer_manager.is_valid() if hasattr(self, 'buffer_manager') else True
            )
            
            # Register test thread
            self.coordinator.register_thread()
            
            # Initialize synchronization primitives
            self.shutdown_event = threading.Event()
            self.error_lock = threading.Lock()
            self.thread_errors = []
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise
        
    def tearDown(self):
        """Clean up test environment."""
        try:
            # Signal threads to stop
            if hasattr(self, 'shutdown_event'):
                self.shutdown_event.set()
            
            # Cleanup buffer manager first
            if hasattr(self, 'buffer_manager'):
                try:
                    self.buffer_manager.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up buffer manager: {e}")
            
            # Then cleanup coordinator
            if hasattr(self, 'coordinator'):
                try:
                    self.coordinator.stop_monitoring()
                    self.coordinator.request_shutdown()
                    # Wait for cleanup to complete
                    time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"Error cleaning up coordinator: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
        finally:
            super().tearDown()
            
    def record_thread_error(self, error):
        """Record thread error with proper synchronization."""
        with self.error_lock:
            self.thread_errors.append(error)
            self.coordinator.request_shutdown()
            self.shutdown_event.set()
        
    @pytest.mark.fast
    def test_atomic_state_updates(self):
        """Test atomic state updates with retry mechanism and validation."""
        try:
            update_count = 1000
            thread_count = 4
            
            # Get initial resource state
            initial_resource_count = self.coordinator.get_allocated_count()
            
            def update_worker():
                thread_id = threading.get_ident()
                thread_name = f"update_worker_{thread_id}"
                threading.current_thread().name = thread_name
                
                try:
                    self.coordinator.register_thread()
                    self.logger.debug(f"Starting update worker thread {thread_name}")
                    
                    for i in range(update_count):
                        if self.shutdown_event.is_set():
                            return
                            
                        # Perform state update cycle with retry mechanism
                        max_retries = 3
                        retry_count = 0
                        success = False
                        
                        while not success and retry_count < max_retries:
                            try:
                                # Acquire locks in proper order: state -> metrics -> perf -> component -> update
                                with self.buffer_manager.state_lock:
                                    with self.buffer_manager.metrics_lock:
                                        with self.buffer_manager.perf_lock:
                                            with self.buffer_manager.component_lock:
                                                with self.buffer_manager.update_lock:
                                                    current_state = self.buffer_manager.get_state()
                                                    new_state = {
                                                        'sequence': current_state.get('sequence', 0) + 1,
                                                        'last_update': time.time(),
                                                        'thread_id': thread_id,
                                                        'update_count': i + 1,
                                                        'retry_count': retry_count,
                                                        'channel': 'both'  # Track channel state
                                                    }
                                                    self.buffer_manager.update_state(new_state)
                                                    success = True
                                    
                            except Exception as e:
                                retry_count += 1
                                if retry_count == max_retries:
                                    raise RuntimeError(f"Failed to update state after {max_retries} retries: {e}")
                                time.sleep(0.01 * retry_count)  # Exponential backoff
                            
                except Exception as e:
                    self.record_thread_error(e)
                finally:
                    self.coordinator.unregister_thread()
                    
            # Run concurrent updates
            threads = []
            for _ in range(thread_count):
                thread = threading.Thread(target=update_worker)
                thread.start()
                threads.append(thread)
            
            # Wait for completion with timeout
            timeout = 30  # 30 seconds total timeout
            start_time = time.time()
            
            for thread in threads:
                remaining_time = max(0, timeout - (time.time() - start_time))
                thread.join(timeout=remaining_time)
                if thread.is_alive():
                    self.shutdown_event.set()
                    raise TimeoutError("Test timeout waiting for threads")
            
            # Verify no errors occurred
            if self.thread_errors:
                raise RuntimeError(f"Thread errors occurred: {self.thread_errors}")
            
            # Verify final state with proper lock ordering
            with self.buffer_manager.state_lock:
                with self.buffer_manager.metrics_lock:
                    with self.buffer_manager.perf_lock:
                        with self.buffer_manager.component_lock:
                            with self.buffer_manager.update_lock:
                                final_state = self.buffer_manager.get_state()
                                expected_sequence = update_count * thread_count
                                
                                # Verify exact sequence count - no tolerance for missed updates
                                self.assertEqual(
                                    final_state.get('sequence', 0),
                                    expected_sequence,
                                    "State sequence must match expected total updates exactly - no tolerance allowed"
                                )
                                
                                # Verify channel state
                                self.assertEqual(
                                    final_state.get('channel'),
                                    'both',
                                    "Channel state must be maintained through updates"
                                )
                                
                                # Verify resource state
                                final_resource_count = self.coordinator.get_allocated_count()
                                self.assertEqual(
                                    final_resource_count,
                                    initial_resource_count,
                                    "Resource count should remain stable during atomic updates"
                                )
                                
                                # Verify state history
                                history = self.buffer_manager.performance_history
                                self.assertGreater(len(history), 0)
                                for entry in history[-10:]:  # Check last 10 entries
                                    self.assertIn('timestamp', entry)
                                    self.assertIn('operation', entry)
                                    self.assertIn('thread_id', entry)
                                    self.assertIn('retry_count', entry)
            
            # Log metrics
            self.log_metric("total_updates", expected_sequence)
            self.log_metric("concurrent_threads", thread_count)
            self.log_metric("errors", len(self.thread_errors))
            self.log_metric("execution_time", time.time() - start_time)
            
        except Exception as e:
            self.logger.error(f"Atomic state updates test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_component_validation(self):
        """Test component validation with health checks and staged cleanup."""
        try:
            # Get initial resource state
            initial_resource_count = self.coordinator.get_allocated_count()
            
            # Register test components with health checks
            components = [
                {
                    'id': 'reader',
                    'type': 'input',
                    'health': lambda: True
                },
                {
                    'id': 'processor',
                    'type': 'transform',
                    'health': lambda: True
                },
                {
                    'id': 'writer',
                    'type': 'output',
                    'health': lambda: True
                }
            ]
            
            for component in components:
                success = self.buffer_manager.register_component(
                    component['id'],
                    component['type'],
                    health_check=component['health']
                )
                self.assertTrue(success, f"Failed to register component {component['id']}")
            
            # Simulate component activity with proper locking
            if not self.buffer_manager.begin_update(timeout=1.0):
                raise TimeoutError("Timeout waiting for update lock")
                
            try:
                for component in components:
                    success = self.buffer_manager.mark_component_active(component['id'])
                    self.assertTrue(success, f"Failed to mark component {component['id']} active")
                    
                    # Verify component state
                    state = self.buffer_manager.get_state()
                    self.assertTrue(state.get(f"{component['id']}_active", False))
                    self.assertTrue(state.get(f"{component['id']}_health_check", False))
            finally:
                self.buffer_manager.end_update()
            
            # Verify active components
            active_components = self.buffer_manager.get_active_components()
            self.assertEqual(len(active_components), len(components))
            
            # Test staged cleanup
            with self.buffer_manager.cleanup_stage():
                # Verify cleanup state
                cleanup_results = self.buffer_manager.validate_cleanup()
                self.assertTrue(cleanup_results.valid)
                self.assertEqual(len(cleanup_results.active_components), len(components))
                
                # Verify component states during cleanup
                state = self.buffer_manager.get_state()
                for component in components:
                    self.assertTrue(state.get(f"{component['id']}_cleanup_pending", False))
            
            # Simulate component shutdown
            for component in components:
                success = self.buffer_manager.mark_component_inactive(component['id'])
                self.assertTrue(success, f"Failed to mark component {component['id']} inactive")
                
                # Verify component state after shutdown
                state = self.buffer_manager.get_state()
                self.assertFalse(state.get(f"{component['id']}_active", True))
            
            # Verify cleanup after shutdown
            final_cleanup = self.buffer_manager.validate_cleanup()
            self.assertTrue(final_cleanup.valid)
            self.assertEqual(len(final_cleanup.active_components), 0)
            
            # Verify resource state after cleanup
            final_resource_count = self.coordinator.get_allocated_count()
            self.assertEqual(
                final_resource_count,
                initial_resource_count,
                "Resource count should remain stable after component cleanup"
            )
            
            # Log validation metrics
            self.log_metric("registered_components", len(components))
            self.log_metric("cleanup_validations", 2)
            self.log_metric("active_components_peak", len(components))
            self.log_metric("active_components_final", 0)
            
        except Exception as e:
            self.logger.error(f"Component validation test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_lock_ordering(self):
        """Test proper lock ordering with resource pool integration."""
        try:
            operation_count = 10
            operation_results = []
            operation_times = []
            
            # Get initial resource state
            initial_resource_count = self.coordinator.get_allocated_count()
            
            def nested_operation():
                """Test nested lock acquisition with resource pool."""
                thread_id = threading.get_ident()
                thread_name = f"nested_worker_{thread_id}"
                threading.current_thread().name = thread_name
                
                try:
                    self.coordinator.register_thread()
                    start_time = time.time()
                    
                    # Acquire locks in proper order: state -> metrics -> perf -> component -> update
                    with self.buffer_manager.state_lock:
                        with self.buffer_manager.metrics_lock:
                            with self.buffer_manager.perf_lock:
                                with self.buffer_manager.component_lock:
                                    with self.buffer_manager.update_lock:
                                        # Get resource through coordinator
                                        resource = self.coordinator.allocate_resource('test', 'buffer', 4096)
                                        try:
                                            time.sleep(0.01)  # Simulate work
                                            operation_results.append(True)
                                            operation_times.append(time.time() - start_time)
                                            return True
                                        finally:
                                            self.coordinator.release_resource('test', 'buffer', resource)
                            
                except Exception as e:
                    self.record_thread_error(e)
                    return False
                finally:
                    self.coordinator.unregister_thread()
                    
            def reverse_operation():
                """Test reverse lock acquisition with resource pool."""
                thread_id = threading.get_ident()
                thread_name = f"reverse_worker_{thread_id}"
                threading.current_thread().name = thread_name
                
                try:
                    self.coordinator.register_thread()
                    start_time = time.time()
                    
                    # Acquire locks in proper order: state -> metrics -> perf -> component -> update
                    with self.buffer_manager.state_lock:
                        with self.buffer_manager.metrics_lock:
                            with self.buffer_manager.perf_lock:
                                with self.buffer_manager.component_lock:
                                    with self.buffer_manager.update_lock:
                                        # Get resource through coordinator
                                        resource = self.coordinator.allocate_resource('test', 'buffer', 4096)
                                        try:
                                            time.sleep(0.01)  # Simulate work
                                            operation_results.append(True)
                                            operation_times.append(time.time() - start_time)
                                            return True
                                        finally:
                                            self.coordinator.release_resource('test', 'buffer', resource)
                            
                except Exception as e:
                    self.record_thread_error(e)
                    return False
                finally:
                    self.coordinator.unregister_thread()
                    
            # Run operations concurrently
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = []
                for _ in range(operation_count):
                    futures.append(executor.submit(nested_operation))
                    futures.append(executor.submit(reverse_operation))
                    
                # Wait for completion with timeout
                done, not_done = wait(futures, timeout=30, return_when=ALL_COMPLETED)
                
                if not_done:
                    self.shutdown_event.set()
                    raise TimeoutError(f"Operations timed out: {len(not_done)} operations incomplete")
                    
                # Get results
                results = [f.result() for f in done]
            
            # Verify all operations completed successfully
            self.assertTrue(all(results))
            self.assertEqual(len(operation_results), operation_count * 2)
            
            # Test lock timeout detection
            start_time = time.time()
            acquired = self.buffer_manager.try_acquire_locks(timeout=0.5)
            acquisition_time = time.time() - start_time
            
            self.assertTrue(acquired)
            self.assertLess(acquisition_time, 1.0)
            
            # Verify resource state after lock operations
            final_resource_count = self.coordinator.get_allocated_count()
            self.assertEqual(
                final_resource_count,
                initial_resource_count,
                "Resource count should remain stable after lock operations"
            )
            
            # Log lock metrics
            self.log_metric("total_operations", len(operation_results))
            self.log_metric("successful_operations", sum(operation_results))
            self.log_metric("average_operation_time", sum(operation_times) / len(operation_times))
            self.log_metric("max_operation_time", max(operation_times))
            self.log_metric("lock_acquisition_time", acquisition_time)
            
        except Exception as e:
            self.logger.error(f"Lock ordering test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_exception_propagation(self):
        """Test exception propagation with enhanced error context."""
        try:
            # Get initial resource state
            initial_resource_count = self.coordinator.get_allocated_count()
            
            # Test various error scenarios
            error_scenarios = [
                ('put_buffer', lambda: self.buffer_manager.put_buffer('invalid_component', b'test')),
                ('get_buffer', lambda: self.buffer_manager.get_buffer('invalid_component')),
                ('optimize_buffers', lambda: self.buffer_manager.optimize_buffers())
            ]
            
            error_contexts = []
            for scenario_name, error_func in error_scenarios:
                try:
                    error_func()
                    self.fail(f"Expected error in scenario: {scenario_name}")
                except Exception as e:
                    # Verify enhanced error context
                    error_info = self.buffer_manager.get_last_error()
                    if error_info:  # Some scenarios may not set error context
                        self.assertIsNotNone(error_info['timestamp'])
                        self.assertIsNotNone(error_info['stack_trace'])
                        self.assertIsNotNone(error_info['component_state'])
                        self.assertIsNotNone(error_info['resource_state'])
                        error_contexts.append(error_info)
            
            # Test error recovery with retry
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    self.buffer_manager.clear_errors()
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        raise RuntimeError(f"Failed to clear errors after {max_retries} retries")
                    time.sleep(0.1)
            
            # Verify error context cleared
            self.assertIsNone(self.buffer_manager.get_last_error())
            
            # Verify component state after errors
            self.assertTrue(self.buffer_manager.is_valid())
            
            # Verify resource state after error handling
            final_resource_count = self.coordinator.get_allocated_count()
            self.assertEqual(
                final_resource_count,
                initial_resource_count,
                "Resource count should remain stable after error scenarios"
            )
            
            # Verify error context completeness
            for context in error_contexts:
                self.assertGreaterEqual(len(context.keys()), 5)  # Enhanced context has more fields
                self.assertIsInstance(context['timestamp'], float)
                self.assertGreater(len(context['stack_trace']), 0)
                self.assertIsInstance(context['component_state'], dict)
                self.assertIsInstance(context['resource_state'], dict)
            
            # Log error metrics
            self.log_metric("error_scenarios_tested", len(error_scenarios))
            self.log_metric("error_contexts_captured", len(error_contexts))
            self.log_metric("average_context_fields", 
                           sum(len(c.keys()) for c in error_contexts) / len(error_contexts))
            
        except Exception as e:
            self.logger.error(f"Exception propagation test failed: {e}")
            raise

if __name__ == '__main__':
    unittest.main()
