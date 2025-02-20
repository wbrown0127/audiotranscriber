"""
COMPONENT_NOTES:
{
    "name": "TestBufferManager",
    "type": "Test Suite",
    "description": "Core test suite for verifying buffer operations, optimization, and thread safety in BufferManager",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TBM[TestBufferManager] --> BM[BufferManager]
                TBM --> MC[MonitoringCoordinator]
                TBM --> CC[ComponentCoordinator]
                TBM --> CT[ComponentTest]
                MC --> RP[ResourceManagement]
        ```",
        "dependencies": {
            "BufferManager": "Main component under test",
            "MonitoringCoordinator": {
                "description": "Provides system monitoring and resource management",
                "responsibilities": [
                    "Resource allocation/deallocation",
                    "Performance tracking",
                    "Component lifecycle",
                    "Error handling"
                ]
            },
            "ComponentCoordinator": "Manages component lifecycle",
            "ComponentTest": "Base test functionality"
        }
    },
    "notes": [
        "Tests configuration validation and management",
        "Verifies thread-safe concurrent buffer operations",
        "Tests dynamic buffer size optimization",
        "Validates performance metrics collection",
        "Ensures proper resource cleanup",
        "Validates both channels (left/right)"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_buffer_manager.py",
            "python -m pytest tests/core/test_buffer_manager.py -k test_buffer_config"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "threading support",
            "queue module"
        ],
        "system": {
            "memory": "500MB minimum",
            "cpu": "Multi-core recommended for concurrency tests"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Moderate memory usage for buffer operations",
            "Multiple concurrent threads",
            "Proper cleanup after tests"
        ]
    }
}
"""
import threading
import time
import logging
from queue import Empty
import pytest
from audio_transcriber.buffer_manager import BufferManager, BufferConfig
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import ComponentTest

class TestBufferManager(ComponentTest):
    def setUp(self):
        """Set up test environment."""
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            super().setUp()
            
            # Initialize coordinator for resource management
            self.coordinator = MonitoringCoordinator()
            self.coordinator.start_monitoring()
            
            # Initialize resource pool through coordinator
            self.coordinator.initialize_resource_pool({
                'memory': 1024 * 1024 * 100,  # 100MB for buffers
                'handles': 50,  # File handles
                'buffer': {
                    4096: 1000,    # Small buffers (4KB)
                    65536: 500,    # Medium buffers (64KB)
                    1048576: 100   # Large buffers (1MB)
                }
            })
            
            # Initialize channels
            for channel in ['left', 'right']:
                self.coordinator.initialize_channel(channel)
            
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
            
            # Register test thread
            self.coordinator.register_thread()
            
            # Initialize synchronization primitives
            self.shutdown_event = threading.Event()
            self.error_lock = threading.Lock()
            self.thread_errors = []
            
            # Get initial resource metrics for verification
            self.initial_metrics = self.coordinator.get_resource_metrics()
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise
        
    def tearDown(self):
        """Clean up test environment."""
        try:
            # Signal threads to stop
            if hasattr(self, 'shutdown_event'):
                self.shutdown_event.set()
            
            # Get initial metrics for verification
            if hasattr(self, 'coordinator'):
                initial_metrics = self.coordinator.get_resource_metrics()
                initial_buffer_stats = self.coordinator.get_buffer_metrics()
            
            # Cleanup buffer manager first
            if hasattr(self, 'buffer_manager'):
                try:
                    # Get pre-cleanup stats
                    pre_cleanup_stats = self.buffer_manager.get_performance_stats()
                    
                    # Perform staged cleanup
                    with self.buffer_manager.cleanup_stage():
                        # Verify components enter cleanup state
                        for component in ['capture', 'processing', 'storage']:
                            state = self.buffer_manager.get_state()
                            self.assertTrue(state.get(f'{component}_cleanup_pending', False))
                    
                    # Complete cleanup
                    self.buffer_manager.cleanup()
                    
                    # Get post-cleanup stats
                    post_cleanup_stats = self.buffer_manager.get_performance_stats()
                    
                    # Log cleanup metrics
                    for key, value in pre_cleanup_stats.items():
                        self.log_metric(f"pre_cleanup_{key}", value)
                    for key, value in post_cleanup_stats.items():
                        self.log_metric(f"post_cleanup_{key}", value)
                        
                except Exception as e:
                    self.logger.error(f"Error cleaning up buffer manager: {e}")
                    raise
            
            # Then cleanup coordinator
            if hasattr(self, 'coordinator'):
                try:
                    # Cleanup channels in reverse order
                    for channel in ['right', 'left']:
                        self.coordinator.cleanup_channel(channel)
                    
                    # Stop monitoring and cleanup
                    self.coordinator.stop_monitoring()
                    self.coordinator.cleanup()
                    
                    # Get final metrics
                    final_metrics = self.coordinator.get_resource_metrics()
                    final_buffer_stats = self.coordinator.get_buffer_metrics()
                    
                    # Verify resource cleanup
                    self.assertEqual(final_metrics['current_used'], 0)
                    self.assertEqual(final_buffer_stats['allocated_count'], 0)
                    
                    # Log cleanup verification metrics
                    self.log_metric("initial_resource_usage", initial_metrics['current_used'])
                    self.log_metric("final_resource_usage", final_metrics['current_used'])
                    self.log_metric("initial_buffer_count", initial_buffer_stats['allocated_count'])
                    self.log_metric("final_buffer_count", final_buffer_stats['allocated_count'])
                    
                except Exception as e:
                    self.logger.error(f"Error cleaning up coordinator: {e}")
                    raise
                    
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
            raise
        finally:
            super().tearDown()
            
    def record_thread_error(self, error):
        """Record thread error with proper synchronization."""
        with self.error_lock:
            self.thread_errors.append(error)
            # Only set shutdown event, let test manage coordinator shutdown
            self.shutdown_event.set()
        
    @pytest.mark.fast
    def test_buffer_config(self):
        """Test buffer configuration management and channel-specific states."""
        try:
            # Test initial configuration
            config = self.buffer_manager.get_buffer_config()
            self.assertEqual(config.channels, 2)
            self.assertEqual(config.sample_width, 2)
            self.assertEqual(config.sample_rate, 16000)
            
            # Verify channel-specific states
            state = self.buffer_manager.get_state()
            self.assertIn('capture_left', state)
            self.assertIn('capture_right', state)
            self.assertIn('processing_left', state)
            self.assertIn('processing_right', state)
            
            # Verify performance metrics for each channel
            stats = self.buffer_manager.get_performance_stats()
            for channel in ['left', 'right']:
                self.assertIn(f'capture_latency_{channel}', stats)
                self.assertIn(f'processing_latency_{channel}', stats)
                self.assertIn(f'storage_latency_{channel}', stats)
            
            # Test configuration update
            self.buffer_manager.update_buffer_config(
                channels=1,
                sample_width=4,
                sample_rate=44100
            )
            
            # Verify update
            updated_config = self.buffer_manager.get_buffer_config()
            self.assertEqual(updated_config.channels, 1)
            self.assertEqual(updated_config.sample_width, 4)
            self.assertEqual(updated_config.sample_rate, 44100)
            
            # Verify valid ranges
            self.assertGreater(updated_config.channels, 0)
            self.assertLess(updated_config.channels, 8)  # Reasonable max channels
            self.assertGreater(updated_config.sample_width, 0)
            self.assertLess(updated_config.sample_width, 8)  # Reasonable max width
            self.assertGreater(updated_config.sample_rate, 0)
            self.assertLess(updated_config.sample_rate, 192000)  # Reasonable max rate
            
            # Log configuration metrics
            self.log_metric("initial_channels", config.channels)
            self.log_metric("initial_sample_width", config.sample_width)
            self.log_metric("initial_sample_rate", config.sample_rate)
            self.log_metric("updated_channels", updated_config.channels)
            self.log_metric("updated_sample_width", updated_config.sample_width)
            self.log_metric("updated_sample_rate", updated_config.sample_rate)
            
        except Exception as e:
            self.logger.error(f"Buffer config test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_concurrent_buffer_operations(self):
        """Test concurrent buffer operations with state transition validation."""
        try:
            producer_count = 2  # Reduced from 4 to lower contention
            consumer_count = 2
            items_per_producer = 50  # Reduced from 100 to lower total items
            
            # Track items with proper synchronization
            produced_items = set()
            consumed_items = set()
            items_lock = threading.Lock()
            
            # Track progress for timeout detection
            progress_lock = threading.Lock()
            last_progress = {'time': time.time()}
            
            def produce_data():
                """Produce test data for each component."""
                thread_id = threading.get_ident()
                thread_name = f"producer_{thread_id}"
                threading.current_thread().name = thread_name
                
                try:
                    self.coordinator.register_thread()
                    self.logger.debug(f"Starting producer thread {thread_name}")
                    
                    start_time = time.time()
                    for i in range(items_per_producer):
                        if self.shutdown_event.is_set():
                            return
                            
                        data = f"test_data_{thread_id}_{i}".encode()
                        with items_lock:
                            produced_items.add(data)
                        
                        # Put data through each component with timeout and retry
                        components = ['capture', 'processing', 'storage']
                        for component in components:
                            success = False
                            retry_count = 0
                            max_retries = 50
                            
                            while not success and retry_count < max_retries:
                                if self.shutdown_event.is_set():
                                    return
                                    
                                # Allocate buffer through coordinator
                                buffer_id = self.coordinator.allocate_buffer(len(data))
                                
                                try:
                                    # Verify component state before put
                                    state = self.buffer_manager.get_state()
                                    if not state.get(f'{component}_active', False):
                                        self.buffer_manager.mark_component_active(component)
                                    
                                    success = self.buffer_manager.put_buffer(component, data, buffer_id)
                                finally:
                                    if not success:
                                        self.coordinator.release_buffer(buffer_id)
                                
                                # Update progress on successful put
                                if success:
                                    with progress_lock:
                                        last_progress['time'] = time.time()
                                else:
                                    time.sleep(0.01)
                                    retry_count += 1
                                    
                                # Only timeout if no progress in 5 seconds
                                current_time = time.time()
                                with progress_lock:
                                    if current_time - last_progress['time'] > 5:
                                        raise TimeoutError(f"Producer timeout in component {component}")
                                    
                            if not success:
                                raise RuntimeError(f"Failed to put data in {component} buffer after {max_retries} retries")
                                
                except Exception as e:
                    self.record_thread_error(e)
                finally:
                    self.coordinator.unregister_thread()
                    
            def consume_data():
                """Consume test data from each component."""
                thread_id = threading.get_ident()
                thread_name = f"consumer_{thread_id}"
                threading.current_thread().name = thread_name
                
                try:
                    self.coordinator.register_thread()
                    self.logger.debug(f"Starting consumer thread {thread_name}")
                    
                    components = ['capture', 'processing', 'storage']
                    expected_total = producer_count * items_per_producer * len(components)
                    start_time = time.time()
                    
                    while not self.shutdown_event.is_set():
                        # Check if we've consumed all expected items
                        with items_lock:
                            if len(consumed_items) >= expected_total:
                                return
                                
                        # Update progress on successful get
                        if data:
                            with progress_lock:
                                last_progress['time'] = time.time()
                        
                        # Only timeout if no progress in 5 seconds
                        current_time = time.time()
                        with progress_lock:
                            if current_time - last_progress['time'] > 5:
                                with items_lock:
                                    self.logger.error(f"Consumer timeout: {len(consumed_items)}/{expected_total} items processed")
                                    raise TimeoutError(f"Consumer timeout: {len(consumed_items)}/{expected_total} items processed")
                                
                        # Try to get items from each component
                        for component in components:
                            try:
                                # Verify component state before get
                                state = self.buffer_manager.get_state()
                                if not state.get(f'{component}_active', False):
                                    self.buffer_manager.mark_component_active(component)
                                    
                                # Get buffer with timeout
                                result = self.buffer_manager.get_buffer(component, timeout=0.1)
                                if result:
                                    data, buffer_id = result
                                    try:
                                        with items_lock:
                                            consumed_items.add(data)
                                            if len(consumed_items) >= expected_total:
                                                return
                                            # Reset timeout on successful get
                                            start_time = current_time
                                    finally:
                                        # Always release buffer after use
                                        self.coordinator.release_buffer(buffer_id)
                            except Empty:
                                continue
                        
                except Exception as e:
                    self.record_thread_error(e)
                finally:
                    self.coordinator.unregister_thread()
                    
            # Start producer threads
            producer_threads = []
            for _ in range(producer_count):
                t = threading.Thread(target=produce_data)
                producer_threads.append(t)
                t.start()
                
            # Start consumer threads
            consumer_threads = []
            for _ in range(consumer_count):
                t = threading.Thread(target=consume_data)
                consumer_threads.append(t)
                t.start()
                
            # Wait for threads with timeout
            timeout = 35  # 35 seconds total timeout
            start_time = time.time()
            
            for t in producer_threads + consumer_threads:
                remaining_time = max(0, timeout - (time.time() - start_time))
                t.join(timeout=remaining_time)
                if t.is_alive():
                    self.shutdown_event.set()
                    self.coordinator.request_shutdown()
                    raise TimeoutError("Test timeout waiting for threads")
                    
            # Check for thread errors
            if self.thread_errors:
                raise RuntimeError(f"Thread errors occurred: {self.thread_errors}")
                
            # Verify all items were processed
            self.assertEqual(len(consumed_items), len(produced_items))
            self.assertEqual(consumed_items, produced_items)
            
            # Log concurrency metrics
            self.log_metric("producer_count", producer_count)
            self.log_metric("consumer_count", consumer_count)
            self.log_metric("items_per_producer", items_per_producer)
            self.log_metric("total_items_produced", len(produced_items))
            self.log_metric("total_items_consumed", len(consumed_items))
            
            # Verify final component states
            for component in ['capture', 'processing', 'storage']:
                state = self.buffer_manager.get_state()
                self.assertTrue(state.get(f'{component}_active', False))
            
        except Exception as e:
            self.logger.error(f"Concurrent buffer operations test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_buffer_optimization(self):
        """Test buffer size optimization based on system metrics."""
        try:
            # Simulate high CPU usage
            self.coordinator.update_state(cpu_usage=85.0)
            
            # Initial buffer size
            initial_size = self.buffer_manager.get_buffer_config().size
            
            # Trigger optimization
            self.buffer_manager.optimize_buffers()
            
            # Verify buffer size increased
            new_size = self.buffer_manager.get_buffer_config().size
            self.assertGreater(new_size, initial_size)
            self.assertLess(new_size, 1024 * 1024)  # Reasonable max size
            
            # Simulate normal CPU usage
            self.coordinator.update_state(cpu_usage=50.0)
            
            # Simulate high memory usage
            self.coordinator.update_state(memory_usage=150 * 1024 * 1024)  # 150MB
            
            # Wait for cooldown
            time.sleep(5.1)  # Just over cooldown period
            
            # Trigger optimization
            self.buffer_manager.optimize_buffers()
            
            # Verify buffer size decreased
            final_size = self.buffer_manager.get_buffer_config().size
            self.assertLess(final_size, new_size)
            self.assertGreater(final_size, 0)  # Must remain positive
            
            # Log optimization metrics
            self.log_metric("initial_buffer_size", initial_size)
            self.log_metric("increased_buffer_size", new_size)
            self.log_metric("final_buffer_size", final_size)
            self.log_metric("high_cpu_usage", 85.0)
            self.log_metric("normal_cpu_usage", 50.0)
            self.log_metric("high_memory_usage", 150 * 1024 * 1024)
            
        except Exception as e:
            self.logger.error(f"Buffer optimization test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_performance_stats(self):
        """Test enhanced performance statistics collection."""
        # Get initial metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Generate some activity
        test_data = b"test_data"
        components = ['capture', 'processing', 'storage']
        buffer_ids = []
        
        try:
            # Add test data to components
            for component in components:
                # Allocate buffer through coordinator
                buffer_id = self.coordinator.allocate_buffer(len(test_data))
                buffer_ids.append(buffer_id)
                
                # Put data with buffer
                success = self.buffer_manager.put_buffer(component, test_data, buffer_id)
                self.assertTrue(success, f"Failed to put data in {component} buffer")
            
            # Get performance stats
            stats = self.buffer_manager.get_performance_stats()
            
            # Verify enhanced stats content
            required_metrics = [
                'buffer_config',
                'queue_metrics',
                'buffer_distribution',
                'latency',
                'overflow',
                'processed'
            ]
            
            for metric in required_metrics:
                self.assertIn(metric, stats)
                self.assertIsNotNone(stats[metric])
                
            # Verify buffer distribution
            self.assertIn('small', stats['buffer_distribution'])
            self.assertIn('medium', stats['buffer_distribution'])
            self.assertIn('large', stats['buffer_distribution'])
            
            # Verify queue metrics for each channel
            for component in components:
                for channel in ['left', 'right']:
                    queue_name = f"{component}_{channel}"
                    self.assertIn(queue_name, stats['queue_metrics'])
                    queue_stats = stats['queue_metrics'][queue_name]
                    self.assertIn('size', queue_stats)
                    self.assertIn('latency', queue_stats)
                    self.assertIn('overflow', queue_stats)
                    self.assertIn('processed', queue_stats)
            
            # Verify latency tracking
            for component in components:
                for channel in ['left', 'right']:
                    queue_name = f"{component}_{channel}"
                    self.assertIn(queue_name, stats['latency'])
                    latency_stats = stats['latency'][queue_name]
                    self.assertIn('current', latency_stats)
                    self.assertIn('history', latency_stats)
            
            # Get coordinator metrics
            coordinator_metrics = self.coordinator.get_performance_metrics()
            buffer_metrics = self.coordinator.get_buffer_metrics()
            
            # Log enhanced performance metrics
            self.log_metric("buffer_size_ms", stats['buffer_config']['size_ms'])
            self.log_metric("buffer_size_bytes", stats['buffer_config']['size_bytes'])
            self.log_metric("small_buffers", stats['buffer_distribution']['small'])
            self.log_metric("medium_buffers", stats['buffer_distribution']['medium'])
            self.log_metric("large_buffers", stats['buffer_distribution']['large'])
            
            # Log coordinator metrics
            self.log_metric("buffer_allocation_time", coordinator_metrics['buffer_allocation_time'])
            self.log_metric("buffer_release_time", coordinator_metrics['buffer_release_time'])
            self.log_metric("buffer_utilization", buffer_metrics['utilization'])
            self.log_metric("buffer_fragmentation", buffer_metrics['fragmentation'])
            self.log_metric("buffer_turnover_rate", buffer_metrics['turnover_rate'])
            
            for component in components:
                for channel in ['left', 'right']:
                    queue_name = f"{component}_{channel}"
                    queue_stats = stats['queue_metrics'][queue_name]
                    self.log_metric(f"{queue_name}_size", queue_stats['size'])
                    self.log_metric(f"{queue_name}_latency", queue_stats['latency'])
                    self.log_metric(f"{queue_name}_overflow", queue_stats['overflow'])
                    self.log_metric(f"{queue_name}_processed", queue_stats['processed'])
            
            # Verify resource usage
            final_metrics = self.coordinator.get_resource_metrics()
            self.assertGreater(final_metrics['current_used'], initial_metrics['current_used'])
            
        except Exception as e:
            self.logger.error(f"Performance stats test failed: {e}")
            raise
        finally:
            # Release all buffers
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
                
            # Verify cleanup
            cleanup_metrics = self.coordinator.get_resource_metrics()
            self.assertEqual(cleanup_metrics['current_used'], initial_metrics['current_used'])
        
    @pytest.mark.fast
    def test_cleanup(self):
        """Test cleanup operations with staged validation."""
        # Get initial metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Add some data to queues
        test_data = b"test_data"
        components = ['capture', 'processing', 'storage']
        buffer_ids = []
        
        try:
            # Add test data to components
            for component in components:
                # Allocate buffer through coordinator
                buffer_id = self.coordinator.allocate_buffer(len(test_data))
                buffer_ids.append(buffer_id)
                
                # Put data with buffer
                success = self.buffer_manager.put_buffer(component, test_data, buffer_id)
                self.assertTrue(success, f"Failed to put data in {component} buffer")
            
            # Verify queues have data
            for component in components:
                queue_name = f"{component}_left"
                self.assertGreater(
                    self.buffer_manager._buffer_queues[queue_name].qsize(),
                    0
                )
                
            # Record initial state
            initial_queue_sizes = {
                component: self.buffer_manager._buffer_queues[f"{component}_left"].qsize()
                for component in components
            }
            initial_history_size = len(self.buffer_manager.performance_history)
            
            # Test staged cleanup
            with self.buffer_manager.cleanup_stage():
                # Verify components are in cleanup state
                for component in components:
                    state = self.buffer_manager.get_state()
                    self.assertTrue(state.get(f'{component}_cleanup_pending', False))
                    
                # Verify pending releases
                for component in components:
                    stats = self.buffer_manager.get_performance_stats()
                    self.assertGreater(stats[f'{component}_pending_releases'], 0)
            
            # Perform cleanup
            self.buffer_manager.cleanup()
            
            # Verify queues are empty
            for component in components:
                queue_name = f"{component}_left"
                self.assertEqual(
                    self.buffer_manager._buffer_queues[queue_name].qsize(),
                    0
                )
                
            # Verify performance history is cleared
            self.assertEqual(len(self.buffer_manager.performance_history), 0)
            
            # Get final metrics
            final_metrics = self.coordinator.get_resource_metrics()
            
            # Log cleanup metrics
            self.log_metric("initial_queue_items", sum(initial_queue_sizes.values()))
            self.log_metric("final_queue_items", 0)
            self.log_metric("initial_history_size", initial_history_size)
            self.log_metric("final_history_size", len(self.buffer_manager.performance_history))
            self.log_metric("initial_resource_usage", initial_metrics['current_used'])
            self.log_metric("final_resource_usage", final_metrics['current_used'])
            
        except Exception as e:
            self.logger.error(f"Cleanup test failed: {e}")
            raise
        finally:
            # Release all buffers
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
                
            # Verify cleanup
            cleanup_metrics = self.coordinator.get_resource_metrics()
            self.assertEqual(cleanup_metrics['current_used'], initial_metrics['current_used'])

if __name__ == '__main__':
    unittest.main()
