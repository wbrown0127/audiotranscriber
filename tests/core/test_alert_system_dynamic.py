#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestAlertSystemDynamic",
    "type": "Test Suite",
    "description": "Advanced test suite for verifying dynamic features of AlertSystem including rate limiting, history tracking, and threshold adjustments",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TAS[TestAlertSystemDynamic] --> CT[ComponentTest]
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
        "Tests rate limiting to prevent alert storms",
        "Verifies alert history tracking and aggregation",
        "Tests dynamic threshold adjustment based on system behavior",
        "Validates alert suppression for repeated conditions",
        "Monitors performance impact of alert operations"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_alert_system_dynamic.py",
            "python -m pytest tests/core/test_alert_system_dynamic.py -k test_rate_limiting"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest with asyncio support"
        ],
        "system": {
            "memory": "1GB minimum",
            "cpu": "AVX2 support required"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Memory usage under 100MB",
            "Uses real system resources",
            "Proper cleanup after each test"
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

class TestAlertSystemDynamic(ComponentTest):
    """Test suite for dynamic AlertSystem functionality."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            await super().asyncSetUp()
            
            # Initialize alert system config with test-specific settings
            self.config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold=100.0,
                storage_latency_threshold=0.5,
                buffer_threshold=90.0,
                rate_limit_interval=0.2,    # Fast rate limiting for testing
                alert_history_size=10,      # Small history for testing
                dynamic_threshold_window=5.0,  # Short window for testing
                check_interval=0.1          # Fast checks for testing
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
                            4096: 5,      # Small test buffers
                            65536: 3,     # Medium test buffers
                            1048576: 1    # Large test buffers
                        }
                    },
                    'threads': {
                        'max': 5,  # Limited threads for testing
                        'timeout': 0.5  # Short timeout for testing
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
                'status': ['normal', 'warning', 'critical'],
                'dynamic': {
                    'enabled': True,
                    'window': 5.0,  # Short window for testing
                    'metrics': ['cpu', 'memory', 'latency', 'buffer']
                }
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
        """Clean up test environment."""
        try:
            # Get initial state for verification
            if hasattr(self, 'coordinator'):
                initial_metrics = await self.coordinator.get_component_metrics('alert_system')
                initial_thresholds = self.alert_system.get_current_thresholds()
            
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
                
                # Verify metrics reset
                final_metrics = await self.coordinator.get_component_metrics('alert_system')
                self.assertEqual(
                    final_metrics.get('alert_count', 0), 0,
                    "Alert metrics not properly reset"
                )
                
                # Verify thresholds reset
                final_thresholds = self.alert_system.get_current_thresholds()
                for metric in ['cpu', 'memory', 'latency', 'buffer']:
                    self.assertEqual(
                        final_thresholds[metric],
                        getattr(self.config, f"{metric}_threshold"),
                        f"{metric} threshold not properly reset"
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
    async def test_rate_limiting(self):
        """Test alert rate limiting functionality."""
        alerts = []
        cpu_loads = []
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Get initial metrics from coordinator
            initial_metrics = await self.coordinator.get_component_metrics('alert_system')
            
            # Generate rapid alerts through real CPU spikes
            for _ in range(10):
                # Create real CPU load
                cpu_load = threading.Thread(target=lambda: [i*i for i in range(10000000)])
                cpu_loads.append(cpu_load)
                cpu_load.start()
                
                # Let coordinator track the real CPU spike
                await asyncio.sleep(0.05)
                
                # Check alert and verify coordinator tracking
                alert = await self.alert_system.check_cpu_usage()
                alerts.append(alert)
                
                # Verify coordinator recorded real metrics
                metrics = await self.coordinator.get_component_metrics('alert_system')
                self.assertIn('cpu_threshold', metrics)
                self.assertIn('cpu_usage', metrics)
                
                # Clean up thread and let CPU recover
                cpu_load.join()
                await asyncio.sleep(0.05)
            
            duration = asyncio.get_event_loop().time() - start_time
            
            # Verify rate limiting through real metrics
            final_metrics = await self.coordinator.get_component_metrics('alert_system')
            triggered_count = final_metrics.get('alert_count', 0) - initial_metrics.get('alert_count', 0)
            
            # Should have fewer triggered alerts than attempts due to rate limiting
            self.assertLess(
                triggered_count,
                len(alerts),
                "Rate limiting should prevent all alerts from triggering"
            )
            
            # Verify alert properties and real state
            for alert in alerts:
                self.assertIsNotNone(alert.timestamp)
                if alert.triggered:
                    # Verify coordinator tracked the real state change
                    metrics = await self.coordinator.get_component_metrics('alert_system')
                    self.assertGreater(metrics.get('cpu_usage', 0), self.config.cpu_threshold)
            
            # Log metrics from real monitoring
            self.log_metric("alert_generation_time", duration)
            self.log_metric("total_alerts", len(alerts))
            self.log_metric("triggered_alerts", triggered_count)
            self.log_metric("alert_rate", len(alerts) / duration)
            self.log_metric("max_cpu_usage", max(
                m.get('cpu_usage', 0) 
                for m in await self.coordinator.get_metric_history('alert_system', 'cpu_usage')
            ))
            
            # Verify rate limiting reset with real load
            await asyncio.sleep(self.config.rate_limit_interval)
            final_cpu_load = threading.Thread(target=lambda: [i*i for i in range(10000000)])
            cpu_loads.append(final_cpu_load)
            final_cpu_load.start()
            await asyncio.sleep(0.1)
            
            alert = await self.alert_system.check_cpu_usage()
            self.assertTrue(alert.triggered, "Alert should trigger after rate limit expires")
            
        except Exception as e:
            self.logger.error(f"Rate limiting test failed: {e}")
            raise
        finally:
            # Clean up any remaining CPU load threads
            for cpu_load in cpu_loads:
                if cpu_load.is_alive():
                    cpu_load.join()
            
            
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_alert_history(self):
        """Test alert history tracking and aggregation."""
        alerts = []
        cpu_loads = []
        
        try:
            # Get initial metrics from coordinator
            initial_metrics = await self.coordinator.get_component_metrics('alert_system')
            
            # Generate alternating normal/high CPU states with real load
            for _ in range(3):
                # Create high CPU load
                cpu_load = threading.Thread(target=lambda: [i*i for i in range(10000000)])
                cpu_loads.append(cpu_load)
                cpu_load.start()
                
                # Let coordinator track the real CPU spike
                await asyncio.sleep(0.1)
                alert = await self.alert_system.check_cpu_usage()
                alerts.append(alert)
                
                # Verify coordinator recorded real metrics
                metrics = await self.coordinator.get_component_metrics('alert_system')
                if alert.triggered:
                    self.assertGreater(
                        metrics.get('cpu_usage', 0),
                        self.config.cpu_threshold
                    )
                
                # Clean up thread and let CPU recover
                cpu_load.join()
                await asyncio.sleep(0.2)
                alert = await self.alert_system.check_cpu_usage()
                alerts.append(alert)
            
            # Verify history through both alert system and coordinator
            history = self.alert_system.get_alert_history()
            self.assertEqual(len(history), len(alerts))
            
            coordinator_history = await self.coordinator.get_metric_history('alert_system', 'cpu_usage')
            self.assertGreater(len(coordinator_history), 0)
            
            # Check aggregation through both sources
            alert_stats = self.alert_system.get_alert_statistics()
            coordinator_stats = await self.coordinator.get_component_metrics('alert_system')
            
            # Verify stats consistency with real metrics
            self.assertEqual(
                alert_stats['total_alerts'],
                coordinator_stats.get('total_alerts', 0)
            )
            
            # Verify alert patterns from real load
            triggered = [a for a in alerts if a.triggered]
            non_triggered = [a for a in alerts if not a.triggered]
            self.assertGreater(len(triggered), 0, "Should have some triggered alerts")
            self.assertGreater(len(non_triggered), 0, "Should have some non-triggered alerts")
            
            # Verify coordinator tracked real state changes
            cpu_history = await self.coordinator.get_metric_history('alert_system', 'cpu_usage')
            high_cpu_states = [m for m in cpu_history if m.get('cpu_usage', 0) > self.config.cpu_threshold]
            normal_cpu_states = [m for m in cpu_history if m.get('cpu_usage', 0) <= self.config.cpu_threshold]
            self.assertGreater(len(high_cpu_states), 0, "Should have high CPU states")
            self.assertGreater(len(normal_cpu_states), 0, "Should have normal CPU states")
            
            # Log comprehensive metrics from real monitoring
            self.log_metric("history_size", len(history))
            self.log_metric("coordinator_history_size", len(coordinator_history))
            self.log_metric("triggered_ratio", alert_stats['triggered_ratio'])
            self.log_metric("total_alerts", alert_stats['total_alerts'])
            self.log_metric("triggered_alerts", len(triggered))
            self.log_metric("non_triggered_alerts", len(non_triggered))
            self.log_metric("high_cpu_states", len(high_cpu_states))
            self.log_metric("normal_cpu_states", len(normal_cpu_states))
            self.log_metric("max_cpu_usage", max(m.get('cpu_usage', 0) for m in cpu_history))
            
        except Exception as e:
            self.logger.error(f"Alert history test failed: {e}")
            raise
        finally:
            # Clean up any remaining CPU load threads
            for cpu_load in cpu_loads:
                if cpu_load.is_alive():
                    cpu_load.join()

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_dynamic_thresholds(self):
        """Test dynamic threshold adjustment based on system behavior."""
        cpu_loads = []
        
        try:
            # Get initial state from both alert system and coordinator
            initial_thresholds = self.alert_system.get_current_thresholds()
            initial_metrics = await self.coordinator.get_component_metrics('alert_system')
            
            # Create varying CPU loads to test threshold adjustment
            for intensity in [1, 2, 3, 2, 1]:  # Varying load intensities
                # Create real CPU load
                cpu_load = threading.Thread(target=lambda: [i*i for i in range(intensity * 5000000)])
                cpu_loads.append(cpu_load)
                cpu_load.start()
                
                # Let coordinator track the real CPU spike
                await asyncio.sleep(0.1)
                
                # Check alert and verify coordinator tracking
                alert = await self.alert_system.check_cpu_usage()
                self.assertIsNotNone(alert)
                
                # Verify coordinator recorded the real metrics
                metrics = await self.coordinator.get_component_metrics('alert_system')
                self.assertIn('cpu_threshold', metrics)
                self.assertIn('cpu_usage', metrics)
                
                # Let CPU stabilize and allow coordinator to track recovery
                cpu_load.join()
                await asyncio.sleep(0.2)
            
            # Get final state from both sources
            final_thresholds = self.alert_system.get_current_thresholds()
            final_metrics = await self.coordinator.get_component_metrics('alert_system')
            
            # Verify threshold adjustment based on real load
            self.assertNotEqual(
                final_thresholds['cpu'],
                initial_thresholds['cpu'],
                "Threshold should adjust based on real system behavior"
            )
            
            # Verify coordinator tracked the threshold changes
            self.assertNotEqual(
                final_metrics.get('cpu_threshold', 0),
                initial_metrics.get('cpu_threshold', 0),
                "Coordinator should track threshold adjustments"
            )
            
            # Verify bounds on real metrics
            self.assertGreater(final_thresholds['cpu'], 0.0)
            self.assertLess(final_thresholds['cpu'], 100.0)
            
            # Log comprehensive metrics from real monitoring
            self.log_metric("initial_threshold", initial_thresholds['cpu'])
            self.log_metric("final_threshold", final_thresholds['cpu'])
            self.log_metric("threshold_delta", final_thresholds['cpu'] - initial_thresholds['cpu'])
            self.log_metric("max_cpu_usage", max(
                m.get('cpu_usage', 0) 
                for m in await self.coordinator.get_metric_history('alert_system', 'cpu_usage')
            ))
            
        except Exception as e:
            self.logger.error(f"Dynamic threshold test failed: {e}")
            raise
        finally:
            # Clean up any remaining CPU load threads
            for cpu_load in cpu_loads:
                if cpu_load.is_alive():
                    cpu_load.join()
            
            
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_alert_suppression(self):
        """Test alert suppression mechanism."""
        cpu_loads = []
        alerts = []
        
        try:
            # Get initial metrics from coordinator
            initial_metrics = await self.coordinator.get_component_metrics('alert_system')
            
            # Generate repeated alerts with real CPU load
            for i in range(5):
                # Create sustained high CPU load
                cpu_load = threading.Thread(target=lambda: [i*i for i in range(10000000)])
                cpu_loads.append(cpu_load)
                cpu_load.start()
                
                # Let coordinator track the real CPU spike
                await asyncio.sleep(0.1)
                
                # Check alert and verify coordinator tracking
                alert = await self.alert_system.check_cpu_usage()
                alerts.append(alert)
                
                # Verify coordinator recorded real metrics
                metrics = await self.coordinator.get_component_metrics('alert_system')
                self.assertIn('cpu_usage', metrics)
                
                # Verify first alert triggers but subsequent ones are suppressed
                if i == 0:
                    self.assertTrue(alert.triggered, "First alert should trigger")
                    # Verify coordinator tracked high CPU state
                    self.assertGreater(metrics.get('cpu_usage', 0), self.config.cpu_threshold)
                else:
                    self.assertFalse(alert.triggered, "Subsequent alerts should be suppressed")
                    # Verify coordinator still sees high CPU despite suppression
                    self.assertGreater(metrics.get('cpu_usage', 0), self.config.cpu_threshold)
                
                # Clean up thread
                cpu_load.join()
                await asyncio.sleep(0.1)
            
            # Wait for suppression to expire
            await asyncio.sleep(self.config.rate_limit_interval)
            
            # Verify alert can trigger again after suppression expires
            final_cpu_load = threading.Thread(target=lambda: [i*i for i in range(10000000)])
            cpu_loads.append(final_cpu_load)
            final_cpu_load.start()
            await asyncio.sleep(0.1)
            
            # Check alert and verify coordinator state
            alert = await self.alert_system.check_cpu_usage()
            self.assertTrue(alert.triggered, "Alert should trigger after suppression expires")
            
            final_metrics = await self.coordinator.get_component_metrics('alert_system')
            self.assertGreater(
                final_metrics.get('cpu_usage', 0),
                self.config.cpu_threshold,
                "CPU should be high for final alert"
            )
            
            # Log comprehensive metrics from real monitoring
            self.log_metric("suppression_interval", self.config.rate_limit_interval)
            self.log_metric("total_attempts", len(alerts))
            self.log_metric("successful_triggers", len([a for a in alerts if a.triggered]))
            self.log_metric("suppressed_alerts", len([a for a in alerts if not a.triggered]))
            self.log_metric("max_cpu_usage", max(
                m.get('cpu_usage', 0) 
                for m in await self.coordinator.get_metric_history('alert_system', 'cpu_usage')
            ))
            
        except Exception as e:
            self.logger.error(f"Alert suppression test failed: {e}")
            raise
        finally:
            # Clean up all CPU load threads
            for cpu_load in cpu_loads:
                if cpu_load.is_alive():
                    cpu_load.join()

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_resource_management(self):
        """Test proper resource management through coordinator."""
        # Note: Verifies centralized resource management through MonitoringCoordinator
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
    async def test_performance_impact(self):
        """Test monitoring of alert system's performance impact."""
        cpu_loads = []
        
        try:
            # Get initial performance metrics
            initial_metrics = self.alert_system.get_performance_metrics()
            self.assertIsNotNone(initial_metrics)
            
            # Track initial resource state
            initial_resource_metrics = await self.alert_system.get_resource_metrics()
            
            # Generate alert activity with real CPU load
            for _ in range(10):
                # Create CPU load
                cpu_load = threading.Thread(target=lambda: [i*i for i in range(10000000)])
                cpu_loads.append(cpu_load)
                cpu_load.start()
                
                # Check alert during high load
                await asyncio.sleep(0.1)
                alert = await self.alert_system.check_cpu_usage()
                self.assertIsNotNone(alert)
                
                # Clean up thread
                cpu_load.join()
            
            # Get updated metrics
            current_metrics = self.alert_system.get_performance_metrics()
            self.assertIsNotNone(current_metrics)
            
            # Get final resource state
            final_resource_metrics = await self.alert_system.get_resource_metrics()
            
            # Verify metrics are being tracked
            self.assertGreater(
                current_metrics['alert_count'],
                initial_metrics['alert_count'],
                "Alert count should increase"
            )
            
            # Verify metric ranges
            self.assertGreaterEqual(current_metrics['cpu_usage'], 0.0)
            self.assertLess(current_metrics['cpu_usage'], 100.0)
            self.assertGreaterEqual(current_metrics['memory_usage'], 0.0)
            
            # Verify no resource leaks
            self.assertEqual(
                initial_resource_metrics['allocated'],
                final_resource_metrics['allocated'],
                "Resource leak detected"
            )
            
            # Log performance metrics
            for key in ['cpu_usage', 'memory_usage', 'alert_count']:
                self.log_metric(f"initial_{key}", initial_metrics[key])
                self.log_metric(f"final_{key}", current_metrics[key])
                self.log_metric(f"{key}_delta", current_metrics[key] - initial_metrics[key])
                
        finally:
            # Clean up any remaining CPU load threads
            for cpu_load in cpu_loads:
                if cpu_load.is_alive():
                    cpu_load.join()
