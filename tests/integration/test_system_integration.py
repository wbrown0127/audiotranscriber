"""
System Integration Test Suite
===========================

Known Issues and Limitations
--------------------------
1. Code Duplication (⚠️ Active Issue)
   - Duplicate code blocks found in multiple test methods
   - Current Status: Cleanup needed in:
     * test_performance_monitoring_integration()
     * test_system_restart_recovery()
     * test_error_propagation()
   - Impact: Code maintenance issues and potential inconsistencies
   - Resolution: Pending cleanup to remove duplicates and add proper error handling

2. Device Configuration (⚠️ Active Issue)
   - Integration tests require specific audio devices
   - Current Status: Tests require proper device setup
   - Required Setup: 
     * WASAPI loopback must be enabled in Windows:
       1. Open Windows Sound Settings
       2. Click "App volume and device preferences"
       3. Enable "Listen to this device" for your output
     * VB-Cable must be installed:
       1. Download from https://vb-audio.com/Cable/
       2. Run installer as administrator
       3. Verify "CABLE Output" appears in Sound devices
   - Impact: Tests will be skipped if devices aren't properly configured
   - Resolution: Improved device validation and setup instructions
"""

import unittest
import time
import threading
from typing import Dict, List
from ..utilities.base import IntegrationTest
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.wasapi_monitor import WASAPIMonitor
from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.cleanup_coordinator import CleanupCoordinator
from audio_transcriber.recovery_logger import RecoveryLogger
from audio_transcriber.state_machine import StateMachine
from audio_transcriber.storage_manager import StorageManager
from audio_transcriber.test_config.device_config import DeviceManager, DeviceType
from audio_transcriber.test_config.scenario_generator import ScenarioGenerator

class TestSystemIntegration(IntegrationTest):
    """
    System-wide integration test suite that validates component interactions.
    Inherits from IntegrationTest to comply with test policy requirements.
    
    Test Policy Compliance:
    - Uses IntegrationTest base class (TEST_POLICY.md section "Test Base Classes")
    - Implements performance metrics logging
    - Follows resource cleanup guidelines
    - Handles WASAPI device requirements
    - Includes comprehensive documentation
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up test environment and initialize components.
        Validates required devices and starts core services.
        """
        super().setUpClass()
        try:
            cls.device_manager = DeviceManager()
            cls.monitoring_coordinator = MonitoringCoordinator()
            cls.cleanup_coordinator = CleanupCoordinator()
            cls.recovery_logger = RecoveryLogger()
            cls.state_machine = StateMachine()
            cls.storage_manager = StorageManager()

            cls.monitoring_coordinator.start_monitoring()
            cls.cleanup_coordinator.start()

            required_devices = [DeviceType.SYSTEM_LOOPBACK, DeviceType.VB_CABLE]
            missing_devices = []
            for device_type in required_devices:
                try:
                    if not cls.device_manager.validate_device(device_type):
                        missing_devices.append(device_type.name)
                except ValueError:
                    missing_devices.append(device_type.name)

            if missing_devices:
                raise unittest.SkipTest(
                    f"Required audio devices not available: {', '.join(missing_devices)}. "
                    "Please ensure WASAPI loopback is enabled and VB-Cable is installed "
                    "from https://vb-audio.com/Cable/"
                )
        except Exception as e:
            raise unittest.SkipTest(f"Test environment setup failed: {str(e)}")

    @classmethod
    def tearDownClass(cls):
        """Clean up test environment and release resources."""
        cls.cleanup_coordinator.request_shutdown()
        cls.monitoring_coordinator.stop_monitoring()
        cls.device_manager.cleanup()
        super().tearDownClass()

    def setUp(self):
        """Set up individual test state and start recovery session."""
        super().setUp()
        self.recovery_logger.start_session()

    def tearDown(self):
        """Clean up test state and end recovery session."""
        self.recovery_logger.end_session()
        super().tearDown()

    def test_performance_monitoring_integration(self):
        """
        Test integration of performance monitoring across components.
        Validates CPU usage, stream health, and buffer statistics.
        """
        wasapi = None
        try:
            wasapi = WASAPIMonitor(self.monitoring_coordinator)
            device_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
            
            # Initialize and verify stream
            start_time = time.perf_counter()
            success = wasapi.initialize_stream(device_index=device_config.device_index)
            self.assertTrue(success)
            self.log_metric("stream_init_time", time.perf_counter() - start_time)
            
            # Monitor performance
            time.sleep(1.0)
            stats = self.monitoring_coordinator.get_performance_stats()
            
            # Verify metrics
            self.assertIn('capture', stats)
            capture_stats = stats['capture']
            self.assertIn('cpu_usage', capture_stats)
            self.assertIn('temperature', capture_stats)
            self.assertIn('stream_health', capture_stats)
            self.assertIn('buffer_size', capture_stats)
            self.assertIn('buffer_duration_ms', capture_stats)
            
            # Log performance metrics
            self.log_metric("cpu_usage", capture_stats['cpu_usage'])
            self.log_metric("buffer_size", capture_stats['buffer_size'])
            self.log_metric("buffer_latency", capture_stats['buffer_duration_ms'])
            
            # Validate values
            self.assertGreaterEqual(capture_stats['cpu_usage'], 0)
            self.assertLess(capture_stats['cpu_usage'], 100)
            self.assertTrue(isinstance(capture_stats['stream_health'], bool))
            
        except Exception as e:
            self.fail(f"Performance monitoring test failed: {str(e)}")
        finally:
            if wasapi:
                wasapi.cleanup()

    def test_system_restart_recovery(self):
        """
        Test system recovery after simulated restart.
        Validates device reconnection and state restoration.
        """
        wasapi = None
        try:
            wasapi = WASAPIMonitor(self.monitoring_coordinator)
            device_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
            
            # Initial setup
            start_time = time.perf_counter()
            success = wasapi.initialize_stream(device_index=device_config.device_index)
            self.assertTrue(success)
            self.log_metric("initial_setup_time", time.perf_counter() - start_time)
            
            # Simulate restart
            restart_start = time.perf_counter()
            self.cleanup_coordinator.start_cleanup()
            time.sleep(0.5)
            
            # Reinitialize
            success = wasapi.initialize_stream(device_index=device_config.device_index)
            self.assertTrue(success)
            self.log_metric("restart_recovery_time", time.perf_counter() - restart_start)
            
            # Verify health
            state = self.monitoring_coordinator.get_state()
            self.assertTrue(state.stream_health)
            
        except Exception as e:
            self.fail(f"System restart recovery test failed: {str(e)}")
        finally:
            if wasapi:
                wasapi.cleanup()

    def test_error_propagation(self):
        """
        Test error propagation through component chain.
        Validates error handling and recovery mechanisms.
        """
        wasapi = None
        try:
            wasapi = WASAPIMonitor(self.monitoring_coordinator)
            device_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
            error_chain = []

            def error_handler(component: str, error: Dict):
                error_chain.append((component, error['error_type']))
                self.log_metric(f"error_{component}", error['error_type'])

            # Register error handlers
            self.monitoring_coordinator.register_error_handler(lambda e: error_handler('monitor', e))
            self.state_machine.register_error_handler(lambda e: error_handler('state', e))
            self.recovery_logger.register_error_handler(lambda e: error_handler('logger', e))

            # Initialize stream
            start_time = time.perf_counter()
            success = wasapi.initialize_stream(device_index=device_config.device_index)
            self.assertTrue(success)
            self.log_metric("stream_init_time", time.perf_counter() - start_time)

            # Simulate error
            error_start = time.perf_counter()
            test_error = {'error_type': 'test_error', 'message': 'Test error propagation'}
            self.monitoring_coordinator.update_state(stream_health=False, error_info=test_error)
            time.sleep(0.5)

            # Verify error chain
            expected_chain = [('monitor', 'test_error'), ('state', 'test_error'), ('logger', 'test_error')]
            self.assertEqual(error_chain, expected_chain)
            self.log_metric("error_propagation_time", time.perf_counter() - error_start)
            
        except Exception as e:
            self.fail(f"Error propagation test failed: {str(e)}")
        finally:
            if wasapi:
                wasapi.cleanup()

if __name__ == '__main__':
    unittest.main()
