#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestAlertSystem",
    "type": "Test Suite",
    "description": "Core test suite for AlertSystem functionality, focusing on configuration validation, threshold monitoring, and error handling",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TAS[TestAlertSystem] --> CT[ComponentTest]
                TAS --> MC[MonitoringCoordinator]
                TAS --> AS[AlertSystem]
                MC --> BM[BufferManager]
                AS -.-> MC
        ```",
        "dependencies": {
            "AlertSystem": "Main component under test",
            "MonitoringCoordinator": "Provides system monitoring and resource management",
            "ComponentTest": "Base test functionality with async support",
            "BufferManager": "Managed by MonitoringCoordinator for buffer operations"
        }
    },
    "notes": [
        "Tests configuration validation and threshold settings",
        "Verifies CPU, memory, storage, and buffer monitoring",
        "Tests error handling and recovery mechanisms",
        "Validates thread registration and cleanup",
        "Tests system behavior under stress conditions"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_alert_system.py",
            "python -m pytest tests/core/test_alert_system.py -k test_config_validation"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "psutil",
            "asyncio"
        ],
        "system": {
            "memory": "500MB minimum",
            "storage": "Fast storage recommended for latency tests"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 10 seconds",
        "resource_usage": [
            "Low memory footprint",
            "Minimal CPU usage",
            "Short-duration storage operations"
        ]
    }
}
"""

import asyncio
import logging
import threading
import pytest
from audio_transcriber.alert_system import AlertSystem, AlertConfig
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import ComponentTest


class TestAlertSystem(ComponentTest):
    """Test suite for AlertSystem functionality."""

    async def asyncSetUp(self):
        """Set up test fixtures before each test method."""
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            await super().asyncSetUp()
            
            # Initialize alert system config with test-specific settings
            self.config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold=100.0,
                storage_latency_threshold=0.5,
                buffer_threshold=90.0,
                check_interval=0.1,  # Faster intervals for testing
                alert_history_size=10,  # Smaller history for testing
                dynamic_threshold_window=5.0  # Shorter window for testing
            )
            
            # Initialize coordinator with test-specific configuration
            coordinator_config = {
                'component': 'alert_system',
                'metrics': {
                    'enabled': True,
                    'interval': 0.1,  # Fast metrics for testing
                    'history_size': 10  # Limited history for testing
                },
                'resources': {
                    'buffer': {
                        'limit': {
                            4096: 10,     # Small test buffers
                            65536: 5,     # Medium test buffers
                            1048576: 2    # Large test buffers
                        }
                    },
                    'threads': {
                        'max': 5,  # Limited threads for testing
                        'timeout': 1.0  # Short timeout for testing
                    }
                },
                'monitoring': {
                    'enabled': True,
                    'stress_threshold': 75.0,  # Lower threshold for testing
                    'check_interval': 0.1  # Fast checks for testing
                }
            }
            
            # Create coordinator with test configuration
            self.coordinator = MonitoringCoordinator(config=coordinator_config)
            
            # Initialize metrics and resource tracking
            await self.coordinator.initialize_component('alert_system', {
                'metrics': ['cpu_usage', 'memory_usage', 'storage_latency', 'buffer_usage'],
                'thresholds': ['cpu', 'memory', 'latency', 'buffer'],
                'status': ['normal', 'warning', 'critical']
            })
            
            # Start monitoring with test configuration
            await self.coordinator.start_monitoring()
            
            # Initialize alert system with coordinator
            self.alert_system = AlertSystem(self.config, coordinator=self.coordinator)
            
            # Register test thread and verify
            thread_id = await self.coordinator.register_thread()
            self.assertIsNotNone(thread_id, "Thread registration failed")
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise

    async def asyncTearDown(self):
        """Clean up test fixtures after each test method."""
        try:
            # Get initial resource state for verification
            if hasattr(self, 'coordinator'):
                initial_metrics = await self.coordinator.get_component_metrics('alert_system')
            
            # Cleanup alert system first
            if hasattr(self, 'alert_system'):
                try:
                    await self.alert_system.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up alert system: {e}")
                    raise
            
            # Verify alert system cleanup
            if hasattr(self, 'coordinator'):
                # Verify all threads unregistered
                active_threads = await self.coordinator.get_active_threads()
                self.assertEqual(len(active_threads), 0, "Not all threads were unregistered")
                
                # Verify metrics cleaned up
                final_metrics = await self.coordinator.get_component_metrics('alert_system')
                self.assertEqual(
                    final_metrics.get('alert_count', 0), 0,
                    "Alert metrics not properly reset"
                )
                
                # Stop and cleanup coordinator
                try:
                    await self.coordinator.stop_monitoring()
                    await self.coordinator.cleanup()
                    
                    # Verify coordinator cleanup
                    self.assertFalse(
                        await self.coordinator.is_monitoring_active(),
                        "Coordinator monitoring not properly stopped"
                    )
                except Exception as e:
                    self.logger.error(f"Error cleaning up coordinator: {e}")
                    raise
                    
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
            raise
        finally:
            await super().asyncTearDown()

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_config_validation(self):
        """Test that AlertConfig properly validates thresholds."""
        # Test valid thresholds
        self.config.validate()  # Should not raise

        # Test invalid CPU threshold
        with self.assertRaises(ValueError):
            invalid_config = AlertConfig(
                cpu_threshold=101.0,
                memory_threshold=100.0,
                storage_latency_threshold=0.5,
                buffer_threshold=90.0
            )
            invalid_config.validate()

        # Test invalid memory threshold
        with self.assertRaises(ValueError):
            invalid_config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold=-1.0,
                storage_latency_threshold=0.5,
                buffer_threshold=90.0
            )
            invalid_config.validate()

        # Test invalid storage latency threshold
        with self.assertRaises(ValueError):
            invalid_config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold=100.0,
                storage_latency_threshold=-0.1,
                buffer_threshold=90.0
            )
            invalid_config.validate()

        # Test invalid buffer threshold
        with self.assertRaises(ValueError):
            invalid_config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold=100.0,
                storage_latency_threshold=0.5,
                buffer_threshold=101.0
            )
            invalid_config.validate()

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_thread_registration(self):
        """Test that AlertSystem properly registers with coordinator."""
        # Get initial thread count
        initial_threads = len(self.coordinator._monitored_threads)
        
        # Create and register a new thread
        thread = threading.Thread(target=lambda: None)
        thread.start()
        self.coordinator.register_thread(thread)
        
        # Verify thread was registered
        self.assertEqual(len(self.coordinator._monitored_threads), initial_threads + 1)
        
        # Cleanup should unregister thread
        await self.alert_system.cleanup()
        self.assertEqual(len(self.coordinator._monitored_threads), initial_threads)
        
        thread.join()

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_cpu_threshold_alert(self):
        """Test CPU usage threshold monitoring."""
        # Create CPU load to trigger alert
        cpu_load = threading.Thread(target=lambda: [i*i for i in range(10000000)])
        cpu_load.start()
        await asyncio.sleep(0.1)  # Allow CPU usage to increase
        
        # Check alert when CPU is high
        alert = await self.alert_system.check_cpu_usage()
        cpu_load.join()
        
        if alert.triggered:
            self.assertIn('CPU usage', alert.message)
        
        # Check alert when CPU is normal
        await asyncio.sleep(0.5)  # Allow CPU to normalize
        alert = await self.alert_system.check_cpu_usage()
        self.assertFalse(alert.triggered)

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_memory_threshold_alert(self):
        """Test memory usage threshold monitoring."""
        # Create memory pressure to trigger alert
        data = []
        for _ in range(10):  # Allocate memory in chunks
            data.append(bytearray(20 * 1024 * 1024))  # 20MB chunks
            await asyncio.sleep(0.1)
            alert = await self.alert_system.check_memory_usage()
            if alert.triggered:
                self.assertIn('Memory usage', alert.message)
                break
        
        # Clear memory and check alert clears
        data.clear()
        await asyncio.sleep(0.5)  # Allow memory to be freed
        alert = await self.alert_system.check_memory_usage()
        self.assertFalse(alert.triggered)

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_storage_latency_alert(self):
        """Test storage write latency monitoring."""
        # Get buffer manager for storage operations
        buffer_manager = self.coordinator.get_buffer_manager()
        
        # Create storage pressure with large buffer operations
        large_buffer = buffer_manager.allocate_buffer(1048576)  # 1MB buffer
        try:
            # Write and read buffer repeatedly to create latency
            for _ in range(100):
                buffer_manager.write_buffer(large_buffer)
                buffer_manager.read_buffer(large_buffer)
            
            # Check alert during high latency operations
            alert = await self.alert_system.check_storage_latency()
            if alert.triggered:
                self.assertIn('Storage latency', alert.message)
            
            # Allow system to stabilize
            await asyncio.sleep(1.0)
            
            # Check alert after stabilization
            alert = await self.alert_system.check_storage_latency()
            self.assertFalse(alert.triggered)
            
        finally:
            if large_buffer:
                buffer_manager.release_buffer(large_buffer)

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_buffer_threshold_alert(self):
        """Test buffer usage threshold monitoring."""
        # Get buffer manager with tier-aware optimization
        buffer_manager = self.coordinator.get_buffer_manager()
        buffers = []
        
        try:
            # Allocate buffers across different tiers
            for size in [4096, 65536, 1048576]:  # Small, Medium, Large
                for _ in range(5):
                    buffer = buffer_manager.allocate_buffer(size)
                    if buffer:
                        buffers.append(buffer)
            
            # Check alert during high buffer usage
            alert = await self.alert_system.check_buffer_usage()
            if alert.triggered:
                self.assertIn('Buffer usage', alert.message)
                
            # Release buffers and verify alert clears
            for buffer in buffers:
                buffer_manager.release_buffer(buffer)
            
            await asyncio.sleep(0.1)
            alert = await self.alert_system.check_buffer_usage()
            self.assertFalse(alert.triggered)
            
        finally:
            # Ensure cleanup in case of test failure
            for buffer in buffers:
                try:
                    buffer_manager.release_buffer(buffer)
                except:
                    pass

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling during monitoring."""
        # Test CPU check error handling by stopping coordinator
        self.coordinator.stop_monitoring()
        alert = await self.alert_system.check_cpu_usage()
        self.assertTrue(alert.triggered)
        self.assertIn('Failed to check CPU', alert.message)
        
        # Restart monitoring
        self.coordinator.start_monitoring()
        
        # Test memory check error handling by corrupting buffer manager
        buffer_manager = self.coordinator.get_buffer_manager()
        buffer_manager._buffers = None  # Corrupt internal state
        
        alert = await self.alert_system.check_memory_usage()
        self.assertTrue(alert.triggered)
        self.assertIn('Failed to check memory', alert.message)

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_rapid_state_transitions(self):
        """Test handling of rapid state changes."""
        transitions = []
        cpu_load = None
        
        try:
            # Create rapid state changes through actual CPU load
            for _ in range(10):  # Reduced iterations for stability
                # Start CPU load
                cpu_load = threading.Thread(target=lambda: [i*i for i in range(10000000)])
                cpu_load.start()
                await asyncio.sleep(0.1)
                alert = await self.alert_system.check_cpu_usage()
                transitions.append(alert.triggered)
                cpu_load.join()
                
                # Let CPU recover
                await asyncio.sleep(0.2)
                alert = await self.alert_system.check_cpu_usage()
                transitions.append(alert.triggered)
            
            # Verify transitions show load pattern
            self.assertGreater(len([t for t in transitions if t]), 0, "No high CPU alerts triggered")
            self.assertGreater(len([t for t in transitions if not t]), 0, "No normal CPU alerts triggered")
            
        finally:
            if cpu_load.is_alive():
                cpu_load.join()

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_stress_monitoring(self):
        """Test monitoring system under stress conditions."""
        start_time = asyncio.get_event_loop().time()
        tasks = []
        buffers = []
        buffer_manager = self.coordinator.get_buffer_manager()
        
        try:
            # Track initial resource state
            initial_metrics = await self.alert_system.get_resource_metrics()
            
            # Create mixed workload
            while asyncio.get_event_loop().time() - start_time < 5:
                # CPU task
                cpu_task = asyncio.create_task(self.alert_system.check_cpu_usage())
                tasks.append(cpu_task)
                
                # Memory task (allocate and free buffer)
                buffer = buffer_manager.allocate_buffer(65536)
                if buffer:
                    buffers.append(buffer)
                memory_task = asyncio.create_task(self.alert_system.check_memory_usage())
                tasks.append(memory_task)
                
                # Storage task
                if buffers:
                    buffer_manager.write_buffer(buffers[-1])
                storage_task = asyncio.create_task(self.alert_system.check_storage_latency())
                tasks.append(storage_task)
                
                # Buffer task
                buffer_task = asyncio.create_task(self.alert_system.check_buffer_usage())
                tasks.append(buffer_task)
                
                await asyncio.sleep(0.1)
            
            # Wait for all tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)
            exceptions = [r for r in results if isinstance(r, Exception)]
            self.assertEqual(len(exceptions), 0, f"Encountered exceptions: {exceptions}")
            
            # Verify resource cleanup
            final_metrics = await self.alert_system.get_resource_metrics()
            self.assertEqual(
                initial_metrics['allocated'],
                final_metrics['allocated'],
                "Resource leak detected"
            )
            
        finally:
            # Clean up buffers
            for buffer in buffers:
                try:
                    buffer_manager.release_buffer(buffer)
                except:
                    pass

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_resource_management(self):
        """Test proper resource management through coordinator."""
        buffer_manager = self.coordinator.get_buffer_manager()
        resource_pool = self.coordinator.get_resource_pool()
        
        # Test buffer allocation across tiers
        small_buffer = buffer_manager.allocate_buffer(4096)
        medium_buffer = buffer_manager.allocate_buffer(65536)
        large_buffer = buffer_manager.allocate_buffer(1048576)
        
        try:
            # Verify allocations
            self.assertIsNotNone(small_buffer, "Failed to allocate small buffer")
            self.assertIsNotNone(medium_buffer, "Failed to allocate medium buffer")
            self.assertIsNotNone(large_buffer, "Failed to allocate large buffer")
            
            # Check metrics tracking
            metrics = await self.alert_system.get_resource_metrics()
            self.assertIn('allocated', metrics)
            self.assertIn('in_use', metrics)
            self.assertIn('peak_usage', metrics)
            
            # Verify proper cleanup
            buffer_manager.release_buffer(small_buffer)
            buffer_manager.release_buffer(medium_buffer)
            buffer_manager.release_buffer(large_buffer)
            
            # Verify resources were released
            final_metrics = await self.alert_system.get_resource_metrics()
            self.assertEqual(final_metrics['in_use'], 0, "Resources not properly released")
            
        finally:
            # Cleanup in case of test failure
            for buffer in [small_buffer, medium_buffer, large_buffer]:
                if buffer:
                    try:
                        buffer_manager.release_buffer(buffer)
                    except:
                        pass

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_coordinator_metrics(self):
        """Test coordinator metrics tracking."""
        # Set initial metrics
        await self.coordinator.set_system_metric('cpu_usage', 50.0)
        await self.coordinator.set_system_metric('memory_usage', 75.0)
        
        # Run checks and verify metric updates
        await self.alert_system.check_cpu_usage()
        await self.alert_system.check_memory_usage()
        
        # Verify metrics were tracked
        metrics = await self.coordinator.get_component_metrics('alert_system')
        self.assertIn('cpu_threshold', metrics)
        self.assertIn('memory_threshold', metrics)
        self.assertIn('last_check_time', metrics)
        
        # Verify threshold history
        thresholds = self.alert_system.get_current_thresholds()
        self.assertEqual(
            thresholds['cpu'],
            await self.coordinator.get_metric('alert_system', 'cpu_threshold')
        )

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_coordinator_status_updates(self):
        """Test coordinator status reporting."""
        # Test normal status
        await self.coordinator.set_system_metric('cpu_usage', 50.0)
        await self.alert_system.check_cpu_usage()
        status = await self.coordinator.get_component_status('alert_system')
        self.assertEqual(status, 'cpu_normal')
        
        # Test warning status
        await self.coordinator.set_system_metric('cpu_usage', 85.0)
        await self.alert_system.check_cpu_usage()
        status = await self.coordinator.get_component_status('alert_system')
        self.assertNotEqual(status, 'cpu_normal')

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_coordinator_error_handling(self):
        """Test coordinator error reporting."""
        # Simulate metric fetch error
        await self.coordinator.set_system_metric_error('cpu_usage', Exception("Test error"))
        await self.alert_system.check_cpu_usage()
        
        # Verify error was reported
        errors = await self.coordinator.get_component_errors('alert_system')
        self.assertGreater(len(errors), 0)
        self.assertIn("CPU check failed", errors[-1])

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_lock_hierarchy(self):
        """Test compliance with lock ordering rules."""
        async with self.coordinator.component_lock('alert_system'):
            # Component lock acquired
            metrics = await self.coordinator.get_component_metrics('alert_system')
            self.assertIsNotNone(metrics)
            
            # Test nested lock acquisition
            async with self.alert_system._state_lock:
                state = self.alert_system.get_alert_history()
                self.assertIsNotNone(state)
                
                async with self.alert_system._metrics_lock:
                    stats = await self.alert_system.get_alert_statistics()
                    self.assertIsNotNone(stats)

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent operations with coordinator."""
        async def run_checks():
            await self.alert_system.check_cpu_usage()
            await self.alert_system.check_memory_usage()
            await self.alert_system.check_storage_latency()
            
        # Run multiple concurrent check operations
        tasks = [run_checks() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify no exceptions occurred
        exceptions = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(len(exceptions), 0, f"Concurrent operations failed: {exceptions}")
        
        # Verify coordinator state is consistent
        metrics = await self.coordinator.get_component_metrics('alert_system')
        self.assertIsNotNone(metrics.get('last_check_time'))
