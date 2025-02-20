#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestMonitoringCoordinator",
    "type": "Test Suite",
    "description": "Core test suite for verifying monitoring coordinator functionality, including metrics tracking, thread management, and system health monitoring",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TMC[TestMonitoringCoordinator] --> MC[MonitoringCoordinator]
                TMC --> CC[ComponentCoordinator]
                TMC --> MM[MonitoringMetrics]
                TMC --> TM[ThreadManager]
                MC --> MM
                MC --> TM
                MC --> CC
        ```",
        "dependencies": {
            "MonitoringCoordinator": "Main component under test",
            "ComponentCoordinator": "Component lifecycle management",
            "MonitoringMetrics": "System metrics tracking",
            "ThreadManager": "Thread lifecycle management"
        }
    },
    "notes": [
        "Tests initialization and validation of monitoring system",
        "Verifies metrics updates and performance tracking",
        "Tests component health monitoring integration",
        "Validates thread registration and management",
        "Tests concurrent metrics updates",
        "Ensures proper shutdown handling"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_monitoring.py",
            "python -m pytest tests/core/test_monitoring.py -k test_metrics_update"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "threading",
            "concurrent.futures",
            "unittest.mock"
        ],
        "system": {
            "memory": "500MB minimum",
            "cpu": "Multi-core recommended for concurrency tests"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 5 seconds",
        "resource_usage": [
            "Multiple concurrent threads",
            "Moderate CPU usage during stress tests",
            "Proper cleanup of threads and resources"
        ]
    }
}
"""
import unittest
import asyncio
import time
import logging
import threading
from unittest.mock import Mock, patch
from threading import Thread, Event, Lock
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED

from audio_transcriber.monitoring_coordinator import (
    MonitoringCoordinator,
    MonitoringMetrics
)
from audio_transcriber.component_coordinator import ComponentCoordinator

class TestMonitoringCoordinator(unittest.TestCase):
    """Test suite for MonitoringCoordinator functionality."""

    def setUp(self):
        """Set up test environment with proper resource management."""
        # Configure logging
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.handlers = []
        self.logger.propagate = False
        
        try:
            # Initialize coordinator with proper resource management
            self.coordinator = MonitoringCoordinator()
            self.coordinator.start_monitoring()
            
            # Initialize resource pool through coordinator
            self.coordinator.initialize_resource_pool({
                'memory': 1024 * 1024 * 100,  # 100MB
                'threads': 4,
                'handles': 100,
                'buffer': {
                    4096: 1000,    # Small buffers
                    65536: 500,    # Medium buffers
                    1048576: 100   # Large buffers
                }
            })
            
            # Mock component coordinator with proper injection
            self.component_coordinator = Mock(spec=ComponentCoordinator)
            self.coordinator.inject_component_coordinator(self.component_coordinator)
            
            # Register main test thread
            self.coordinator.register_thread()
            
            # Initialize synchronization primitives
            self.shutdown_event = Event()
            self.error_lock = Lock()
            self.thread_errors = []
            
            # Initialize channel-specific resources
            for channel in ['left', 'right']:
                self.coordinator.initialize_channel(channel)
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise

    def tearDown(self):
        """Clean up test environment with proper resource cleanup."""
        try:
            # Signal threads to stop
            if hasattr(self, 'shutdown_event'):
                self.shutdown_event.set()
            
            if hasattr(self, 'coordinator'):
                try:
                    # Cleanup channel resources first
                    for channel in ['right', 'left']:  # Reverse order
                        try:
                            self.coordinator.cleanup_channel(channel)
                        except Exception as e:
                            self.logger.error(f"Error cleaning up channel {channel}: {e}")
                    
                    # Stop monitoring
                    self.coordinator.stop_monitoring()
                    
                    # Request shutdown and wait for cleanup
                    self.coordinator.request_shutdown()
                    time.sleep(0.1)  # Allow time for cleanup
                    
                except Exception as e:
                    self.logger.error(f"Error during coordinator cleanup: {e}")
                    
            # Clean up mocks
            if hasattr(self, 'component_coordinator'):
                self.component_coordinator.reset_mock()
                
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

    def test_initialization_validation(self):
        """Test monitoring coordinator initialization validation."""
        try:
            # Test initialization state tracking
            coordinator = MonitoringCoordinator()
            self.assertTrue(hasattr(coordinator, '_metrics_initialized'))
            
            # Test metrics initialization
            metrics = coordinator.get_metrics()
            self.assertIsInstance(metrics, MonitoringMetrics)
            
            # Test metrics update before initialization
            coordinator._metrics_initialized = False
            coordinator.update_metrics(cpu_usage=50.0)
            self.assertTrue(coordinator._metrics_initialized)
            
            # Test metrics validation during initialization
            metrics = coordinator.get_metrics()
            self.assertEqual(metrics.cpu_usage, 50.0)
            self.assertGreaterEqual(metrics.cpu_usage, 0.0)
            self.assertLess(metrics.cpu_usage, 100.0)
            
        except Exception as e:
            self.logger.error(f"Initialization validation test failed: {e}")
            raise

    def test_metrics_update(self):
        """Test monitoring metrics updates with channel-specific tracking."""
        try:
            # Test with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            # Update system-wide metrics
                            self.coordinator.update_metrics(
                                cpu_usage=50.0,
                                memory_usage=80,
                                disk_usage=60.0,
                                error_count=2
                            )
                            
                            # Update channel-specific metrics
                            for channel in ['left', 'right']:
                                self.coordinator.update_channel_metrics(
                                    channel,
                                    {
                                        'cpu_usage': 40.0,
                                        'memory_usage': 70,
                                        'buffer_usage': 50.0,
                                        'latency': 0.1
                                    }
                                )
                            
                            # Verify system-wide metrics
                            metrics = self.coordinator.get_metrics()
                            self.assertEqual(metrics.cpu_usage, 50.0)
                            self.assertEqual(metrics.memory_usage, 80)
                            self.assertEqual(metrics.disk_usage, 60.0)
                            self.assertEqual(metrics.error_count, 2)
                            
                            # Verify metric ranges
                            self.assertGreaterEqual(metrics.cpu_usage, 0.0)
                            self.assertLess(metrics.cpu_usage, 100.0)
                            self.assertGreaterEqual(metrics.memory_usage, 0)
                            self.assertGreaterEqual(metrics.disk_usage, 0.0)
                            self.assertLess(metrics.disk_usage, 100.0)
                            self.assertGreaterEqual(metrics.error_count, 0)
                            
                            # Verify channel-specific metrics
                            for channel in ['left', 'right']:
                                channel_metrics = self.coordinator.get_channel_metrics(channel)
                                self.assertEqual(channel_metrics['cpu_usage'], 40.0)
                                self.assertEqual(channel_metrics['memory_usage'], 70)
                                self.assertEqual(channel_metrics['buffer_usage'], 50.0)
                                self.assertEqual(channel_metrics['latency'], 0.1)
                                
                                # Verify channel metric ranges
                                self.assertGreaterEqual(channel_metrics['cpu_usage'], 0.0)
                                self.assertLess(channel_metrics['cpu_usage'], 100.0)
                                self.assertGreaterEqual(channel_metrics['memory_usage'], 0)
                                self.assertGreaterEqual(channel_metrics['buffer_usage'], 0.0)
                                self.assertLess(channel_metrics['buffer_usage'], 100.0)
                                self.assertGreater(channel_metrics['latency'], 0.0)
            
        except Exception as e:
            self.logger.error(f"Metrics update test failed: {e}")
            raise

    def test_performance_stats(self):
        """Test performance statistics tracking with channel-specific stats."""
        try:
            # Test with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            # Add system-wide performance stats
                            stats = {
                                'cpu_usage': 30.0,
                                'memory_usage': 50,
                                'latency': 0.1
                            }
                            self.coordinator.update_performance_stats('test_component', stats)
                            
                            # Add channel-specific performance stats
                            for channel in ['left', 'right']:
                                channel_stats = {
                                    'cpu_usage': 25.0,
                                    'memory_usage': 40,
                                    'latency': 0.08,
                                    'buffer_usage': 45.0,
                                    'queue_size': 100
                                }
                                self.coordinator.update_channel_performance_stats(
                                    'test_component',
                                    channel,
                                    channel_stats
                                )
                            
                            # Get current system-wide stats
                            current_stats = self.coordinator.get_performance_stats()
                            self.assertIn('test_component', current_stats)
                            self.assertEqual(
                                current_stats['test_component']['stats'],
                                stats
                            )
                            
                            # Verify system-wide stat ranges
                            component_stats = current_stats['test_component']['stats']
                            self.assertGreaterEqual(component_stats['cpu_usage'], 0.0)
                            self.assertLess(component_stats['cpu_usage'], 100.0)
                            self.assertGreaterEqual(component_stats['memory_usage'], 0)
                            self.assertGreater(component_stats['latency'], 0.0)
                            
                            # Get and verify channel-specific stats
                            for channel in ['left', 'right']:
                                channel_stats = self.coordinator.get_channel_performance_stats(
                                    'test_component',
                                    channel
                                )
                                self.assertEqual(channel_stats['cpu_usage'], 25.0)
                                self.assertEqual(channel_stats['memory_usage'], 40)
                                self.assertEqual(channel_stats['latency'], 0.08)
                                self.assertEqual(channel_stats['buffer_usage'], 45.0)
                                self.assertEqual(channel_stats['queue_size'], 100)
                                
                                # Verify channel stat ranges
                                self.assertGreaterEqual(channel_stats['cpu_usage'], 0.0)
                                self.assertLess(channel_stats['cpu_usage'], 100.0)
                                self.assertGreaterEqual(channel_stats['memory_usage'], 0)
                                self.assertGreater(channel_stats['latency'], 0.0)
                                self.assertGreaterEqual(channel_stats['buffer_usage'], 0.0)
                                self.assertLess(channel_stats['buffer_usage'], 100.0)
                                self.assertGreaterEqual(channel_stats['queue_size'], 0)
            
        except Exception as e:
            self.logger.error(f"Performance stats test failed: {e}")
            raise

    def test_component_health_monitoring(self):
        """Test component health monitoring integration."""
        try:
            # Mock component coordinator response
            self.component_coordinator.verify_system_health.return_value = True
            
            # Start monitoring
            self.coordinator.start_monitoring()
            
            # Let monitoring run briefly
            time.sleep(0.1)
            
            # Verify health check was called
            self.component_coordinator.verify_system_health.assert_called()
            
            # Verify metrics reflect system health
            metrics = self.coordinator.get_metrics()
            self.assertTrue(metrics.stream_health)
            
            # Verify monitoring is active
            self.assertTrue(self.coordinator._monitoring_active)
            self.assertTrue(hasattr(self.coordinator, '_monitoring_timer'))
            
        except Exception as e:
            self.logger.error(f"Component health monitoring test failed: {e}")
            raise

    def test_error_handling(self):
        """Test error handling and metrics update."""
        try:
            # Simulate error
            error = Exception("Test error")
            self.coordinator.handle_error(error, "test_component")
            
            # Verify error was handled
            metrics = self.coordinator.get_metrics()
            self.assertEqual(metrics.error_count, 1)
            
            # Verify component coordinator was notified
            self.component_coordinator.transition_component_state.assert_called_once()
            
            # Verify error details
            error_info = self.coordinator.get_last_error()
            self.assertEqual(error_info['component'], "test_component")
            self.assertIsNotNone(error_info['timestamp'])
            self.assertIsNotNone(error_info['stack_trace'])
            
        except Exception as e:
            self.logger.error(f"Error handling test failed: {e}")
            raise

    def test_monitoring_lifecycle(self):
        """Test monitoring start/stop lifecycle."""
        try:
            # Start monitoring
            self.coordinator.start_monitoring()
            self.assertTrue(self.coordinator._monitoring_active)
            self.assertTrue(hasattr(self.coordinator, '_monitoring_timer'))
            
            # Verify monitoring is functioning
            time.sleep(0.1)
            self.component_coordinator.verify_system_health.assert_called()
            
            # Stop monitoring
            self.coordinator.stop_monitoring()
            self.assertFalse(self.coordinator._monitoring_active)
            self.assertFalse(hasattr(self.coordinator, '_monitoring_timer'))
            
            # Verify monitoring has stopped
            call_count = self.component_coordinator.verify_system_health.call_count
            time.sleep(0.1)
            self.assertEqual(
                call_count,
                self.component_coordinator.verify_system_health.call_count
            )
            
        except Exception as e:
            self.logger.error(f"Monitoring lifecycle test failed: {e}")
            raise

    def test_thread_management(self):
        """Test thread registration and monitoring."""
        try:
            completion_event = Event()
            
            def test_thread():
                try:
                    # Register thread with coordinator
                    thread_id = self.coordinator.register_thread()
                    self.assertIn(thread_id, self.coordinator._threads)
                    
                    # Do some work
                    time.sleep(0.1)
                    
                    # Unregister thread
                    self.coordinator.unregister_thread(thread_id)
                    self.assertNotIn(thread_id, self.coordinator._threads)
                    
                    completion_event.set()
                    
                except Exception as e:
                    self.record_thread_error(e)
                    
            # Create and start test thread
            thread = Thread(target=test_thread, name="TestThread")
            thread.start()
            
            # Wait for completion with timeout
            completed = completion_event.wait(timeout=1.0)
            self.assertTrue(completed, "Thread operation timed out")
            
            # Check for errors
            self.assertEqual(len(self.thread_errors), 0, 
                           f"Thread errors occurred: {self.thread_errors}")
            
            # Cleanup
            thread.join(timeout=0.5)
            self.assertFalse(thread.is_alive(), "Thread failed to terminate")
            
        except Exception as e:
            self.logger.error(f"Thread management test failed: {e}")
            raise

    def test_concurrent_metrics_update(self):
        """Test concurrent metrics updates."""
        try:
            thread_count = 5
            updates_per_thread = 100
            completion_count = 0
            completion_lock = Lock()
            
            def update_metrics(thread_id):
                try:
                    # Register thread
                    self.coordinator.register_thread()
                    thread_name = f"MetricsThread_{thread_id}"
                    threading.current_thread().name = thread_name
                    self.logger.debug(f"Starting metrics thread {thread_name}")
                    
                    for i in range(updates_per_thread):
                        if self.shutdown_event.is_set():
                            return
                            
                        try:
                            self.coordinator.update_metrics(
                                cpu_usage=float(i),
                                memory_usage=i*2
                            )
                            time.sleep(0.001)  # Small delay to reduce contention
                        except Exception as e:
                            pass  # Suppress error logging
                            raise
                            
                    # Track completion
                    nonlocal completion_count
                    with completion_lock:
                        completion_count += 1
                        
                except Exception as e:
                    self.record_thread_error(e)
                finally:
                    self.coordinator.unregister_thread()
                    
            # Create and run threads using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
                futures = [executor.submit(update_metrics, i) for i in range(thread_count)]
                
                # Wait for all futures to complete with timeout
                done, not_done = wait(futures, timeout=5.0, return_when=ALL_COMPLETED)
                
                # Check if any futures didn't complete
                if not_done:
                    self.shutdown_event.set()
                    raise TimeoutError(f"{len(not_done)} threads did not complete within timeout")
                
                # Check for any exceptions
                for future in done:
                    try:
                        future.result()  # This will raise any exceptions that occurred
                    except Exception as e:
                        self.record_thread_error(e)
                    
            # Verify all threads completed
            self.assertEqual(completion_count, thread_count, 
                           f"Not all threads completed. Expected {thread_count}, got {completion_count}")
            
            # Check for errors
            self.assertEqual(len(self.thread_errors), 0, 
                           f"Thread errors occurred: {self.thread_errors}")
            
            # Verify metrics are consistent
            metrics = self.coordinator.get_metrics()
            self.assertIsInstance(metrics.cpu_usage, float)
            self.assertIsInstance(metrics.memory_usage, int)
            self.assertGreaterEqual(metrics.cpu_usage, 0.0)
            self.assertLess(metrics.cpu_usage, 100.0)
            self.assertGreaterEqual(metrics.memory_usage, 0)
            
        except Exception as e:
            # Only log test results directory on failure
            print(f"\nTest results available in: tests/results/{time.strftime('%Y%m%d_%H%M%S')}")
            raise

    def test_buffer_metrics(self):
        """Test buffer-related metrics tracking with channel-specific buffers."""
        try:
            # Test with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            # Update system-wide buffer metrics
                            self.coordinator.update_metrics(
                                capture_queue_size=100,
                                processing_queue_size=50,
                                storage_queue_size=75,
                                capture_buffer_size=1024,
                                processing_buffer_size=512,
                                storage_buffer_size=768
                            )
                            
                            # Update channel-specific buffer metrics
                            for channel in ['left', 'right']:
                                self.coordinator.update_channel_buffer_metrics(
                                    channel,
                                    {
                                        'capture_queue_size': 80,
                                        'processing_queue_size': 40,
                                        'storage_queue_size': 60,
                                        'capture_buffer_size': 512,
                                        'processing_buffer_size': 256,
                                        'storage_buffer_size': 384,
                                        'buffer_utilization': 75.0
                                    }
                                )
                            
                            # Verify system-wide metrics
                            metrics = self.coordinator.get_metrics()
                            self.assertEqual(metrics.capture_queue_size, 100)
                            self.assertEqual(metrics.processing_queue_size, 50)
                            self.assertEqual(metrics.storage_queue_size, 75)
                            self.assertEqual(metrics.capture_buffer_size, 1024)
                            self.assertEqual(metrics.processing_buffer_size, 512)
                            self.assertEqual(metrics.storage_buffer_size, 768)
                            
                            # Verify system-wide metric ranges
                            self.assertGreaterEqual(metrics.capture_queue_size, 0)
                            self.assertGreaterEqual(metrics.processing_queue_size, 0)
                            self.assertGreaterEqual(metrics.storage_queue_size, 0)
                            self.assertGreater(metrics.capture_buffer_size, 0)
                            self.assertGreater(metrics.processing_buffer_size, 0)
                            self.assertGreater(metrics.storage_buffer_size, 0)
                            
                            # Verify channel-specific buffer metrics
                            for channel in ['left', 'right']:
                                channel_metrics = self.coordinator.get_channel_buffer_metrics(channel)
                                self.assertEqual(channel_metrics['capture_queue_size'], 80)
                                self.assertEqual(channel_metrics['processing_queue_size'], 40)
                                self.assertEqual(channel_metrics['storage_queue_size'], 60)
                                self.assertEqual(channel_metrics['capture_buffer_size'], 512)
                                self.assertEqual(channel_metrics['processing_buffer_size'], 256)
                                self.assertEqual(channel_metrics['storage_buffer_size'], 384)
                                self.assertEqual(channel_metrics['buffer_utilization'], 75.0)
                                
                                # Verify channel metric ranges
                                self.assertGreaterEqual(channel_metrics['capture_queue_size'], 0)
                                self.assertGreaterEqual(channel_metrics['processing_queue_size'], 0)
                                self.assertGreaterEqual(channel_metrics['storage_queue_size'], 0)
                                self.assertGreater(channel_metrics['capture_buffer_size'], 0)
                                self.assertGreater(channel_metrics['processing_buffer_size'], 0)
                                self.assertGreater(channel_metrics['storage_buffer_size'], 0)
                                self.assertGreaterEqual(channel_metrics['buffer_utilization'], 0.0)
                                self.assertLessEqual(channel_metrics['buffer_utilization'], 100.0)
            
        except Exception as e:
            self.logger.error(f"Buffer metrics test failed: {e}")
            raise

    def test_transcription_metrics(self):
        """Test transcription metrics tracking with channel-specific transcriptions."""
        try:
            # Test with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            # Update system-wide transcription metrics
                            self.coordinator.update_metrics(
                                last_transcription="Test transcription",
                                transcription_confidence=0.95
                            )
                            
                            # Update channel-specific transcription metrics
                            for channel in ['left', 'right']:
                                self.coordinator.update_channel_transcription_metrics(
                                    channel,
                                    {
                                        'last_transcription': f"Test {channel} channel",
                                        'transcription_confidence': 0.90,
                                        'word_count': 10,
                                        'speaker_confidence': 0.85,
                                        'noise_level': -60.0
                                    }
                                )
                            
                            # Verify system-wide metrics
                            metrics = self.coordinator.get_metrics()
                            self.assertEqual(metrics.last_transcription, "Test transcription")
                            self.assertEqual(metrics.transcription_confidence, 0.95)
                            
                            # Verify system-wide metric ranges
                            self.assertGreaterEqual(metrics.transcription_confidence, 0.0)
                            self.assertLessEqual(metrics.transcription_confidence, 1.0)
                            self.assertIsInstance(metrics.last_transcription, str)
                            self.assertGreater(len(metrics.last_transcription), 0)
                            
                            # Verify channel-specific transcription metrics
                            for channel in ['left', 'right']:
                                channel_metrics = self.coordinator.get_channel_transcription_metrics(channel)
                                self.assertEqual(channel_metrics['last_transcription'], f"Test {channel} channel")
                                self.assertEqual(channel_metrics['transcription_confidence'], 0.90)
                                self.assertEqual(channel_metrics['word_count'], 10)
                                self.assertEqual(channel_metrics['speaker_confidence'], 0.85)
                                self.assertEqual(channel_metrics['noise_level'], -60.0)
                                
                                # Verify channel metric ranges
                                self.assertGreaterEqual(channel_metrics['transcription_confidence'], 0.0)
                                self.assertLessEqual(channel_metrics['transcription_confidence'], 1.0)
                                self.assertGreaterEqual(channel_metrics['word_count'], 0)
                                self.assertGreaterEqual(channel_metrics['speaker_confidence'], 0.0)
                                self.assertLessEqual(channel_metrics['speaker_confidence'], 1.0)
                                self.assertLessEqual(channel_metrics['noise_level'], 0.0)
            
        except Exception as e:
            self.logger.error(f"Transcription metrics test failed: {e}")
            raise

    def test_shutdown_handling(self):
        """Test shutdown request handling."""
        try:
            # Request shutdown
            self.coordinator.request_shutdown()
            
            # Verify shutdown state
            self.assertTrue(self.coordinator.is_shutdown_requested())
            
            # Verify component coordinator cleanup was called
            self.component_coordinator.cleanup_all.assert_called_once()
            
            # Verify monitoring has stopped
            self.assertFalse(self.coordinator._monitoring_active)
            self.assertFalse(hasattr(self.coordinator, '_monitoring_timer'))
            
            # Verify all threads are unregistered
            self.assertEqual(len(self.coordinator._threads), 0)
            
        except Exception as e:
            self.logger.error(f"Shutdown handling test failed: {e}")
            raise

if __name__ == '__main__':
    unittest.main()
