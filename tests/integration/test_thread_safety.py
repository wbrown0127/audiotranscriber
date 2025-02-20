"""
Thread safety test suite for the Audio Transcriber system.
Tests concurrent access patterns, state management, and synchronization mechanisms.
"""

import unittest
import threading
import time
import queue
import asyncio
import os
import logging
from typing import List, Set
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.state_machine import RecoveryState
from audio_transcriber.storage_manager import StorageManager
from audio_transcriber.cleanup_coordinator import CleanupCoordinator

class TestThreadSafety(unittest.TestCase):
    def setUp(self):
        """Set up test environment."""
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_data")
        os.makedirs(self.test_dir, exist_ok=True)
        
        self.coordinator = MonitoringCoordinator()
        self.storage = StorageManager(self.test_dir, self.coordinator)
        self.cleanup = CleanupCoordinator(self.coordinator)
        
        # Track observed states for verification
        self.observed_states: Set[str] = set()
        self.state_lock = threading.Lock()
        
        # Track thread errors
        self.thread_errors: List[Exception] = []
        self.error_lock = threading.Lock()
        
        # Register state change callback and ensure initial state is tracked
        self.coordinator.state_machine.register_state_change_callback(self._state_change_callback)
        with self.state_lock:
            self.observed_states.add(self.coordinator.state_machine.get_current_state())
        
        self.coordinator.start_monitoring()
        
    def tearDown(self):
        """Clean up test environment."""
        self.coordinator.stop_monitoring()
        self.coordinator.request_shutdown()
        self.coordinator.wait_for_cleanup(timeout=5.0)
        
        # Clean up test directory
        for root, dirs, files in os.walk(self.test_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.test_dir)
        
    def _state_change_callback(self, old_state: RecoveryState, new_state: RecoveryState):
        """Track state changes for verification."""
        with self.state_lock:
            # Track both old and new states to ensure we don't miss transitions
            self.observed_states.add(old_state.value)
            self.observed_states.add(new_state.value)
            # Log state transition for debugging
            logging.debug(f"State transition: {old_state.value} -> {new_state.value}")

    def test_concurrent_state_transitions(self):
        """Test concurrent state transitions with proper propagation."""
        transition_count = 100
        thread_count = 4
        threads = []
        
        def trigger_transitions():
            try:
                start_time = time.time()
                for _ in range(transition_count):
                    if time.time() - start_time > 30:  # 30 second timeout
                        raise TimeoutError("Test timeout in trigger_transitions")
                        
                    # Simulate error condition
                    self.coordinator.handle_error(
                        Exception("Test error"), 
                        "test_component"
                    )
                    time.sleep(0.001)  # Allow other threads to interleave
                    # Reset error state
                    self.coordinator.reset_error_state()
                    time.sleep(0.001)
            except Exception as e:
                with self.error_lock:
                    self.thread_errors.append(e)
                self.coordinator.request_shutdown()
        
        # Create and start threads
        for _ in range(thread_count):
            t = threading.Thread(target=trigger_transitions)
            threads.append(t)
            t.start()
            
        # Wait for threads with timeout
        timeout = 35  # 35 seconds total timeout
        start_time = time.time()
        
        for t in threads:
            remaining_time = max(0, timeout - (time.time() - start_time))
            t.join(timeout=remaining_time)
            if t.is_alive():
                self.coordinator.request_shutdown()
                raise TimeoutError("Test timeout waiting for threads")
                
        # Check for thread errors
        if self.thread_errors:
            raise RuntimeError(f"Thread errors occurred: {self.thread_errors}")
            
        # Verify state transitions
        with self.state_lock:
            self.assertIn("failed", self.observed_states)
            self.assertIn("idle", self.observed_states)

    def test_lock_ordering_compliance(self):
        """Test lock ordering compliance under concurrent access."""
        access_count = 100
        thread_count = 4
        successful_accesses = queue.Queue()
        
        def access_with_ordering():
            try:
                start_time = time.time()
                for _ in range(access_count):
                    if time.time() - start_time > 30:  # 30 second timeout
                        raise TimeoutError("Test timeout in access_with_ordering")
                        
                    # Test coordinator's acquire_locks utility
                    locks = [
                        self.coordinator.state_lock,
                        self.coordinator.cleanup_lock,
                        self.coordinator.threads_lock,
                        self.coordinator.perf_lock
                    ]
                    
                    if self.coordinator.acquire_locks(*locks, timeout=1.0):
                        try:
                            successful_accesses.put(1)
                            time.sleep(0.001)  # Simulate work
                        finally:
                            self.coordinator.release_locks(*locks)
            except Exception as e:
                with self.error_lock:
                    self.thread_errors.append(e)
                self.coordinator.request_shutdown()
                        
        # Create and start threads
        threads = []
        for _ in range(thread_count):
            t = threading.Thread(target=access_with_ordering)
            threads.append(t)
            t.start()
            
        # Wait for threads with timeout
        timeout = 35  # 35 seconds total timeout
        start_time = time.time()
        
        for t in threads:
            remaining_time = max(0, timeout - (time.time() - start_time))
            t.join(timeout=remaining_time)
            if t.is_alive():
                self.coordinator.request_shutdown()
                raise TimeoutError("Test timeout waiting for threads")
                
        # Check for thread errors
        if self.thread_errors:
            raise RuntimeError(f"Thread errors occurred: {self.thread_errors}")
            
        # Verify all accesses were successful
        self.assertEqual(successful_accesses.qsize(), access_count * thread_count)

    async def async_test_storage_thread_safety(self):
        """Test storage manager thread safety with concurrent operations."""
        write_count = 100
        thread_count = 4
        successful_writes = queue.Queue()
        
        # Initialize storage
        await self.storage.initialize()
        
        def write_data():
            try:
                start_time = time.time()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    for i in range(write_count):
                        if time.time() - start_time > 30:  # 30 second timeout
                            raise TimeoutError("Test timeout in write_data")
                            
                        data = f"test_data_{threading.get_ident()}_{i}".encode()
                        filename = os.path.join(self.test_dir, f"test_{i}.dat")
                        
                        # Perform write operation
                        loop.run_until_complete(
                            self.storage.optimized_write(data, filename)
                        )
                        successful_writes.put(1)
                        
                finally:
                    loop.close()
            except Exception as e:
                with self.error_lock:
                    self.thread_errors.append(e)
                self.coordinator.request_shutdown()
                
        # Create and start threads
        threads = []
        for _ in range(thread_count):
            t = threading.Thread(target=write_data)
            threads.append(t)
            t.start()
            
        # Wait for threads with timeout
        timeout = 35  # 35 seconds total timeout
        start_time = time.time()
        
        for t in threads:
            remaining_time = max(0, timeout - (time.time() - start_time))
            t.join(timeout=remaining_time)
            if t.is_alive():
                self.coordinator.request_shutdown()
                raise TimeoutError("Test timeout waiting for threads")
                
        # Check for thread errors
        if self.thread_errors:
            raise RuntimeError(f"Thread errors occurred: {self.thread_errors}")
            
        # Verify all writes were successful
        self.assertEqual(successful_writes.qsize(), write_count * thread_count)
        
        # Verify storage state
        stats = self.storage.get_io_stats()
        self.assertIsNotNone(stats.buffer_usage)
        self.assertGreaterEqual(stats.write_throughput, 0)

    def test_storage_thread_safety(self):
        """Run async storage thread safety test."""
        asyncio.run(self.async_test_storage_thread_safety())

    def test_cleanup_coordination(self):
        """Test cleanup coordination between components."""
        thread_count = 4
        components = ['capture', 'processor', 'storage']
        cleanup_complete = threading.Event()
        
        def component_cleanup(component: str):
            try:
                start_time = time.time()
                if time.time() - start_time > 30:  # 30 second timeout
                    raise TimeoutError(f"Test timeout in component_cleanup for {component}")
                    
                # Simulate component work
                time.sleep(0.1)
                # Mark component cleanup complete
                self.coordinator.mark_component_cleanup_complete(component)
            except Exception as e:
                with self.error_lock:
                    self.thread_errors.append(e)
                self.coordinator.request_shutdown()
            
        # Start cleanup in background thread
        def monitor_cleanup():
            try:
                start_time = time.time()
                retry_count = 0
                max_retries = 500  # 5 seconds max (with 0.01s sleep)
                
                while not self.coordinator.are_all_components_cleaned_up():
                    if time.time() - start_time > 5:  # 5 second timeout
                        raise TimeoutError("Cleanup monitoring timeout")
                    if retry_count >= max_retries:
                        raise RuntimeError("Max cleanup monitoring retries exceeded")
                        
                    time.sleep(0.01)
                    retry_count += 1
                    
                cleanup_complete.set()
            except Exception as e:
                with self.error_lock:
                    self.thread_errors.append(e)
                self.coordinator.request_shutdown()
            
        monitor_thread = threading.Thread(target=monitor_cleanup)
        monitor_thread.start()
        
        # Start component cleanup threads
        threads = []
        for component in components:
            for _ in range(thread_count):
                t = threading.Thread(target=component_cleanup, args=(component,))
                threads.append(t)
                t.start()
                
        # Wait for threads with timeout
        timeout = 35  # 35 seconds total timeout
        start_time = time.time()
        
        for t in threads:
            remaining_time = max(0, timeout - (time.time() - start_time))
            t.join(timeout=remaining_time)
            if t.is_alive():
                self.coordinator.request_shutdown()
                raise TimeoutError("Test timeout waiting for threads")
                
        # Wait for cleanup completion
        if not cleanup_complete.wait(timeout=5.0):
            self.coordinator.request_shutdown()
            raise TimeoutError("Cleanup completion timeout")
            
        remaining_time = max(0, timeout - (time.time() - start_time))
        monitor_thread.join(timeout=remaining_time)
        if monitor_thread.is_alive():
            self.coordinator.request_shutdown()
            raise TimeoutError("Monitor thread timeout")
            
        # Check for thread errors
        if self.thread_errors:
            raise RuntimeError(f"Thread errors occurred: {self.thread_errors}")
        
        # Verify final state
        self.assertTrue(self.coordinator.are_all_components_cleaned_up())

    def test_error_handling_propagation(self):
        """Test error handling and state propagation under concurrent errors."""
        error_count = 50
        thread_count = 4
        components = ['capture', 'processor', 'storage']
        
        def generate_errors():
            try:
                start_time = time.time()
                for i in range(error_count):
                    if time.time() - start_time > 30:  # 30 second timeout
                        raise TimeoutError("Test timeout in generate_errors")
                        
                    component = components[i % len(components)]
                    error = Exception(f"Test error {i} from {component}")
                    self.coordinator.handle_error(error, component)
                    time.sleep(0.001)  # Allow other threads to interleave
            except Exception as e:
                with self.error_lock:
                    self.thread_errors.append(e)
                self.coordinator.request_shutdown()
                
        # Create and start threads
        threads = []
        for _ in range(thread_count):
            t = threading.Thread(target=generate_errors)
            threads.append(t)
            t.start()
            
        # Wait for threads with timeout
        timeout = 35  # 35 seconds total timeout
        start_time = time.time()
        
        for t in threads:
            remaining_time = max(0, timeout - (time.time() - start_time))
            t.join(timeout=remaining_time)
            if t.is_alive():
                self.coordinator.request_shutdown()
                raise TimeoutError("Test timeout waiting for threads")
                
        # Check for thread errors
        if self.thread_errors:
            raise RuntimeError(f"Thread errors occurred: {self.thread_errors}")
            
        # Verify error handling
        state = self.coordinator.get_state()
        self.assertGreater(state.error_count, 0)
        with self.state_lock:
            self.assertIn("failed", self.observed_states)

    def test_concurrent_performance_monitoring(self):
        """Test concurrent performance monitoring and stats collection."""
        update_count = 100
        thread_count = 4
        components = ['capture', 'processor', 'storage']
        
        def update_performance():
            try:
                start_time = time.time()
                for i in range(update_count):
                    if time.time() - start_time > 30:  # 30 second timeout
                        raise TimeoutError("Test timeout in update_performance")
                        
                    for component in components:
                        stats = {
                            'cpu': 50 + (i % 10),
                            'memory': 30 + (i % 5),
                            'timestamp': time.time()
                        }
                        self.coordinator.update_performance_stats(component, stats)
                        
                        if self.coordinator.should_check_health():
                            current_stats = self.coordinator.get_performance_stats()
                            self.assertIn(component, current_stats)
            except Exception as e:
                with self.error_lock:
                    self.thread_errors.append(e)
                self.coordinator.request_shutdown()
                        
        # Create and start threads
        threads = []
        for _ in range(thread_count):
            t = threading.Thread(target=update_performance)
            threads.append(t)
            t.start()
            
        # Wait for threads with timeout
        timeout = 35  # 35 seconds total timeout
        start_time = time.time()
        
        for t in threads:
            remaining_time = max(0, timeout - (time.time() - start_time))
            t.join(timeout=remaining_time)
            if t.is_alive():
                self.coordinator.request_shutdown()
                raise TimeoutError("Test timeout waiting for threads")
                
        # Check for thread errors
        if self.thread_errors:
            raise RuntimeError(f"Thread errors occurred: {self.thread_errors}")
            
        # Verify final stats
        final_stats = self.coordinator.get_performance_stats()
        for component in components:
            self.assertIn(component, final_stats)
            self.assertIn('stats', final_stats[component])
            self.assertIn('timestamp', final_stats[component])

if __name__ == '__main__':
    unittest.main()
