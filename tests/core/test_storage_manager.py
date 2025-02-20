"""
COMPONENT_NOTES:
{
    "name": "TestStorageManager",
    "type": "Test Suite",
    "description": "Core test suite for verifying storage management functionality, including write performance, emergency recovery, and buffer operations",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TSM[TestStorageManager] --> SM[StorageManager]
                TSM --> CT[ComponentTest]
                SM --> WB[WriteBuffer]
                SM --> ER[EmergencyRecovery]
                SM --> PM[PerformanceMetrics]
                SM --> FS[FileSystem]
        ```",
        "dependencies": {
            "StorageManager": "Main component under test",
            "ComponentTest": "Base test functionality",
            "WriteBuffer": "Buffer management",
            "EmergencyRecovery": "Data recovery operations",
            "PerformanceMetrics": "Performance tracking",
            "FileSystem": "File I/O operations"
        }
    },
    "notes": [
        "Tests storage write performance and metrics",
        "Verifies emergency data recovery mechanism",
        "Tests write buffer management",
        "Validates buffer optimization",
        "Ensures proper cleanup operations",
        "Tests async I/O operations"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_storage_manager.py",
            "python -m pytest tests/core/test_storage_manager.py -k test_write_performance"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "pytest-asyncio",
            "asyncio"
        ],
        "system": {
            "storage": "Fast storage for write tests",
            "permissions": "Write access to test directories"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "High disk I/O during write tests",
            "Moderate memory usage for buffers",
            "Proper cleanup of test files"
        ]
    }
}
"""
import os
import pytest
import asyncio
from audio_transcriber.storage_manager import StorageManager
from tests.utilities.base import ComponentTest

class TestStorageManager(ComponentTest):
    async def asyncSetUp(self):
        """Set up test environment."""
        await super().setUp()
        self.test_dir = os.path.join("tests", "results", "test_storage")
        os.makedirs(self.test_dir, exist_ok=True)
        
        # Initialize coordinator
        from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
        self.coordinator = MonitoringCoordinator()
        self.coordinator.start_monitoring()
        
        # Initialize resource pool through coordinator
        self.coordinator.initialize_resource_pool({
            'memory': 1024 * 1024 * 100,  # 100MB for buffers
            'storage': 1024 * 1024 * 1000,  # 1GB for storage
            'handles': 100,  # File handles
            'buffer': {
                4096: 1000,    # Small buffers
                65536: 500,    # Medium buffers
                1048576: 100   # Large buffers
            }
        })
        
        # Initialize channels
        for channel in ['left', 'right']:
            self.coordinator.initialize_channel(channel)
        
        # Create storage manager with coordinator
        self.storage = StorageManager(
            directory=self.test_dir,
            coordinator=self.coordinator
        )
        
        # Initialize storage
        await self.storage.initialize()
        
    async def asyncTearDown(self):
        """Clean up test environment."""
        try:
            # Ensure all async operations are complete
            if hasattr(self, 'storage'):
                # Get initial resource metrics
                initial_metrics = self.coordinator.get_resource_metrics()
                
                # Cleanup storage
                await self.storage.cleanup_buffer()
                await self.storage.emergency_flush()
                await self.storage.close()
                
                # Wait for any pending tasks
                tasks = [t for t in asyncio.all_tasks() 
                        if t is not asyncio.current_task()]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # Verify resources were released
                final_metrics = self.coordinator.get_resource_metrics()
                assert final_metrics['current_used'] <= initial_metrics['current_used']
            
            # Cleanup coordinator
            if hasattr(self, 'coordinator'):
                # Cleanup channels in reverse order
                for channel in ['right', 'left']:
                    self.coordinator.cleanup_channel(channel)
                self.coordinator.stop_monitoring()
                await self.coordinator.cleanup()
            
            # Remove test directory
            import shutil
            if os.path.exists(self.test_dir):
                # Ensure files are closed before removal
                await asyncio.sleep(0.1)
                shutil.rmtree(self.test_dir, ignore_errors=True)
        finally:
            await super().tearDown()
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_write_performance(self):
        """Test storage write performance and metrics."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Create test data (1 second of audio)
        test_data = b'\x00\x00' * 48000
        filename = os.path.join(self.test_dir, "test.raw")
        
        # Allocate buffer through coordinator
        buffer_id = self.coordinator.allocate_buffer(len(test_data))
        
        try:
            # Measure write performance
            start_time = asyncio.get_event_loop().time()
            await self.storage.optimized_write(test_data, filename, buffer_id)
            duration = asyncio.get_event_loop().time() - start_time
            
            # Get performance stats from coordinator
            perf_metrics = self.coordinator.get_performance_metrics()
            
            # Verify performance metrics
            self.assertLess(perf_metrics['write_latency'], 0.5)  # Max 500ms latency
            self.assertGreater(perf_metrics['throughput'], 0)
            
            # Log performance metrics
            self.log_metric("write_latency", perf_metrics['write_latency'])
            self.log_metric("throughput", perf_metrics['throughput'])
            self.log_metric("write_duration", duration)
            self.log_metric("data_size", len(test_data))
            self.log_metric("buffer_utilization", perf_metrics['buffer_utilization'])
            self.log_metric("io_operations", perf_metrics['io_operations'])
            
        finally:
            # Release buffer
            self.coordinator.release_buffer(buffer_id)
            
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_emergency_recovery(self):
        """Test emergency data recovery mechanism."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Create test data
        test_data = b'\x00\x00' * 48000
        
        # Allocate buffer through coordinator
        buffer_id = self.coordinator.allocate_buffer(len(test_data))
        
        try:
            # Simulate write failure by adding to buffer
            self.storage.write_buffer.append((test_data, "failed.raw", buffer_id))
            
            # Get initial buffer metrics from coordinator
            initial_buffer_metrics = self.coordinator.get_buffer_metrics()
            self.log_metric("initial_buffer_size", initial_buffer_metrics['total_size'])
            
            # Trigger and wait for emergency flush
            flush_task = asyncio.create_task(self.storage.emergency_flush())
            await flush_task
            
            # Verify backup files were created
            backup_files = os.listdir(self.storage.emergency_dir)
            self.assertGreater(len(backup_files), 0)
            
            # Get recovery metrics from coordinator
            recovery_metrics = self.coordinator.get_recovery_metrics()
            
            # Log recovery metrics
            self.log_metric("backup_files_created", len(backup_files))
            self.log_metric("recovery_time", recovery_metrics['recovery_time'])
            self.log_metric("data_recovered", recovery_metrics['data_recovered'])
            self.log_metric("recovery_success_rate", recovery_metrics['success_rate'])
            
            # Get final buffer metrics
            final_buffer_metrics = self.coordinator.get_buffer_metrics()
            self.log_metric("final_buffer_size", final_buffer_metrics['total_size'])
            
        finally:
            # Release buffer
            self.coordinator.release_buffer(buffer_id)
            
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_buffer_management(self):
        """Test write buffer management and optimization."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Test data with different sizes
        small_data = b'\x00' * 1000
        large_data = b'\x00' * 100000
        
        # Add to write buffer through coordinator
        buffer_id_small = self.coordinator.allocate_buffer(len(small_data))
        buffer_id_large = self.coordinator.allocate_buffer(len(large_data))
        
        # Write data to buffers
        self.storage.write_buffer.append((small_data, "small.raw", buffer_id_small))
        self.storage.write_buffer.append((large_data, "large.raw", buffer_id_large))
        
        # Get buffer stats through coordinator
        buffer_stats = self.coordinator.get_buffer_metrics()
        
        # Verify buffer allocation
        self.assertEqual(buffer_stats['allocated_count'], 2)
        self.assertGreater(buffer_stats['total_size'], 0)
        
        # Log buffer metrics
        self.log_metric("buffer_count", buffer_stats['allocated_count'])
        self.log_metric("buffer_total_size", buffer_stats['total_size'])
        self.log_metric("buffer_avg_size", buffer_stats['average_size'])
        
        # Test buffer cleanup
        await self.storage.cleanup_buffer()
        
        # Verify resources were released
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_thread_safety(self):
        """Test thread safety of storage operations."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Test data
        test_data = b'\x00\x00' * 1000
        operation_count = 100
        thread_count = 10
        
        # Track operations
        successful_writes = 0
        failed_writes = 0
        write_lock = asyncio.Lock()
        
        async def concurrent_write(thread_id):
            nonlocal successful_writes, failed_writes
            try:
                # Allocate buffer through coordinator
                buffer_id = self.coordinator.allocate_buffer(len(test_data))
                
                try:
                    # Write to file
                    filename = os.path.join(self.test_dir, f"test_{thread_id}.raw")
                    await self.storage.optimized_write(test_data, filename, buffer_id)
                    async with write_lock:
                        successful_writes += 1
                finally:
                    # Release buffer
                    self.coordinator.release_buffer(buffer_id)
                    
            except Exception as e:
                async with write_lock:
                    failed_writes += 1
                    self.log_error(f"Write error in thread {thread_id}: {e}")
        
        # Run concurrent operations
        tasks = []
        for i in range(thread_count):
            for j in range(operation_count):
                tasks.append(asyncio.create_task(concurrent_write(i)))
        
        await asyncio.gather(*tasks)
        
        # Verify results
        total_expected = thread_count * operation_count
        self.assertEqual(successful_writes + failed_writes, total_expected)
        self.assertGreater(successful_writes / total_expected, 0.95)  # 95% success rate
        
        # Verify file integrity
        for i in range(thread_count):
            filename = os.path.join(self.test_dir, f"test_{i}.raw")
            self.assertTrue(os.path.exists(filename))
        
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
        
        # Get thread safety metrics from coordinator
        thread_metrics = self.coordinator.get_thread_metrics()
        
        # Log thread safety metrics
        self.log_metric("concurrent_writes_total", total_expected)
        self.log_metric("concurrent_writes_success", successful_writes)
        self.log_metric("concurrent_writes_failed", failed_writes)
        self.log_metric("success_rate", successful_writes / total_expected)
        self.log_metric("max_concurrent_threads", thread_metrics['max_concurrent'])
        self.log_metric("thread_contention_count", thread_metrics['contention_count'])

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_backup_procedures(self):
        """Test comprehensive backup procedures."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Test data with version tracking
        test_data_v1 = b'\x00\x00' * 1000
        test_data_v2 = b'\x01\x01' * 1000
        filename = os.path.join(self.test_dir, "test.raw")
        
        # Allocate buffers through coordinator
        buffer_id_v1 = self.coordinator.allocate_buffer(len(test_data_v1))
        buffer_id_v2 = self.coordinator.allocate_buffer(len(test_data_v2))
        
        try:
            # Write initial version
            await self.storage.optimized_write(test_data_v1, filename, buffer_id_v1)
            
            # Create incremental backup
            backup_id = await self.storage.create_backup(incremental=True)
            self.assertIsNotNone(backup_id)
            
            # Write updated version
            await self.storage.optimized_write(test_data_v2, filename, buffer_id_v2)
            
            # Create full backup
            full_backup_id = await self.storage.create_backup(incremental=False)
            self.assertIsNotNone(full_backup_id)
            
            # Verify backups
            backup_info = await self.storage.verify_backup(backup_id)
            self.assertTrue(backup_info['verified'])
            self.assertEqual(backup_info['size'], len(test_data_v1))
            
            full_backup_info = await self.storage.verify_backup(full_backup_id)
            self.assertTrue(full_backup_info['verified'])
            self.assertEqual(full_backup_info['size'], len(test_data_v2))
            
            # Test backup rotation
            rotation_config = {
                'max_backups': 5,
                'max_age_days': 7,
                'min_free_space': 1024 * 1024 * 100  # 100MB
            }
            await self.storage.configure_backup_rotation(rotation_config)
            
            # Create multiple backups to trigger rotation
            for i in range(6):
                await self.storage.create_backup(incremental=False)
                
            # Verify rotation
            backups = await self.storage.list_backups()
            self.assertLessEqual(len(backups), rotation_config['max_backups'])
            
            # Log backup metrics
            self.log_metric("backup_count", len(backups))
            self.log_metric("total_backup_size", sum(b['size'] for b in backups))
            self.log_metric("avg_backup_size", sum(b['size'] for b in backups) / len(backups))
            
            # Get backup performance metrics from coordinator
            backup_metrics = self.coordinator.get_backup_metrics()
            self.log_metric("backup_throughput", backup_metrics['throughput'])
            self.log_metric("backup_latency", backup_metrics['latency'])
            
        finally:
            # Release buffers
            self.coordinator.release_buffer(buffer_id_v1)
            self.coordinator.release_buffer(buffer_id_v2)
            
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test comprehensive error handling."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Test file system errors
        invalid_dir = "/invalid/directory/path"
        with self.assertRaises(FileNotFoundError):
            storage = StorageManager(
                directory=invalid_dir,
                coordinator=self.coordinator
            )
            await storage.initialize()
        
        # Test permission errors
        test_file = os.path.join(self.test_dir, "readonly.raw")
        with open(test_file, 'wb') as f:
            f.write(b'\x00' * 100)
        os.chmod(test_file, 0o444)  # Make read-only
        
        buffer_id = self.coordinator.allocate_buffer(100)
        try:
            with self.assertRaises(PermissionError):
                await self.storage.optimized_write(b'\x01' * 100, test_file, buffer_id)
        finally:
            self.coordinator.release_buffer(buffer_id)
        
        # Test disk space errors
        huge_data = b'\x00' * (1024 * 1024 * 1024)  # 1GB
        with self.assertRaises(OSError):
            # Should fail before buffer allocation
            await self.storage.optimized_write(huge_data, "huge_file.raw")
        
        # Test recovery from write errors
        test_data = b'\x00' * 1000
        filename = os.path.join(self.test_dir, "test.raw")
        
        buffer_id = self.coordinator.allocate_buffer(len(test_data))
        try:
            # Simulate write failure
            self.storage._simulate_write_error = True
            with self.assertRaises(IOError):
                await self.storage.optimized_write(test_data, filename, buffer_id)
            
            # Verify error recovery
            self.storage._simulate_write_error = False
            await self.storage.optimized_write(test_data, filename, buffer_id)
            self.assertTrue(os.path.exists(filename))
        finally:
            self.coordinator.release_buffer(buffer_id)
        
        # Test buffer overflow handling
        large_data = b'\x00' * (1024 * 1024 * 10)  # 10MB
        buffer_ids = []
        try:
            # Try to overflow buffer pool
            for _ in range(100):
                try:
                    buffer_id = self.coordinator.allocate_buffer(len(large_data))
                    buffer_ids.append(buffer_id)
                except Exception:
                    break  # Buffer pool exhausted
            
            # Verify buffer limits enforced
            buffer_metrics = self.coordinator.get_buffer_metrics()
            self.assertLessEqual(
                buffer_metrics['total_size'],
                buffer_metrics['max_size']
            )
        finally:
            # Release all allocated buffers
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
        
        # Get error metrics from coordinator
        error_metrics = self.coordinator.get_error_metrics()
        
        # Log error handling metrics
        self.log_metric("total_errors", error_metrics['total'])
        self.log_metric("recovered_errors", error_metrics['recovered'])
        self.log_metric("unrecovered_errors", error_metrics['unrecovered'])
        self.log_metric("error_types", len(error_metrics['error_types']))
        self.log_metric("max_error_rate", error_metrics['max_error_rate'])
        
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
