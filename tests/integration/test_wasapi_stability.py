"""
COMPONENT_NOTES:
{
    "name": "TestWASAPIStability",
    "type": "Integration Test Suite",
    "description": "Integration test suite for verifying WASAPI stability features, including stream initialization, recovery, and cleanup procedures",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TWS[TestWASAPIStability] --> MC[MonitoringCoordinator]
                TWS --> WM[WASAPIMonitor]
                TWS --> AAC[AdaptiveAudioCapture]
                TWS --> IT[IntegrationTest]
                TWS --> DM[DeviceManager]
                TWS --> SG[ScenarioGenerator]
        ```",
        "dependencies": {
            "MonitoringCoordinator": "System monitoring",
            "WASAPIMonitor": "WASAPI interface management",
            "AdaptiveAudioCapture": "Audio capture system",
            "IntegrationTest": "Base test functionality",
            "DeviceManager": "Audio device management",
            "ScenarioGenerator": "Test scenario generation"
        }
    },
    "notes": [
        "System audio capture through loopback",
        "VB-Cable device integration",
        "Device switching and recovery",
        "Concurrent device capture",
        "Stream recovery mechanisms",
        "Buffer handling and performance"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/integration/test_wasapi_stability.py",
            "python -m pytest tests/integration/test_wasapi_stability.py -k test_stream_recovery --duration 3600"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "pyaudiowpatch",
            "asyncio"
        ],
        "system": {
            "os": "Windows 10/11 with WASAPI support",
            "audio": "VB-Cable and system loopback enabled",
            "memory": "2GB minimum"
        }
    },
    "performance": {
        "execution_time": "Tests may take several minutes (slow marker)",
        "resource_usage": [
            "High CPU/memory usage during tests",
            "Requires actual audio hardware",
            "May impact system audio during testing"
        ]
    }
}
"""

import time
import pytest
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.wasapi_monitor import WASAPIMonitor
from audio_transcriber.audio_capture import AdaptiveAudioCapture
from tests.utilities.base import IntegrationTest
from audio_transcriber.test_config.device_config import DeviceManager, DeviceType
from audio_transcriber.test_config.scenario_generator import ScenarioGenerator, ScenarioType

class TestWASAPIStability(IntegrationTest):
    """Integration test suite for WASAPI stability features.
    
    This test class verifies the stability and reliability of WASAPI
    audio capture under various conditions and scenarios.
    
    Key Features Tested:
        - System audio capture reliability
        - Device switching and recovery
        - Concurrent device handling
        - Stream recovery mechanisms
        - Buffer management and performance
    
    Attributes:
        coordinator (MonitoringCoordinator): System monitoring
        device_manager (DeviceManager): Audio device management
        scenario_generator (ScenarioGenerator): Test scenario generation
    
    Example:
        class TestCustomScenario(TestWASAPIStability):
            def test_custom_recovery(self):
                scenario = self.scenario_generator.create_custom_scenario()
                self.run_recovery_test(scenario)
    """
    def setUp(self):
        """Set up test environment with real WASAPI devices."""
        super().setUp()
        self.coordinator = MonitoringCoordinator()
        self.coordinator.start_monitoring()
        self.device_manager = DeviceManager()
        self.scenario_generator = ScenarioGenerator(self.device_manager)
        
        # Log available devices
        devices = self.device_manager.get_all_configs()
        for device in devices:
            self.log_metric(f"device_{device.device_type.name}", {
                'name': device.name,
                'index': device.device_index,
                'channels': device.channels,
                'sample_rate': device.sample_rate
            })
        
    def tearDown(self):
        """Clean up test environment."""
        try:
            self.coordinator.stop_monitoring()
            self.coordinator.request_shutdown()
            self.device_manager.cleanup()
        finally:
            super().tearDown()
        
    @pytest.mark.slow
    def test_system_audio_capture(self):
        """Test system audio capture through loopback device.
        
        Verifies the system's ability to capture audio through the
        Windows system loopback device. This test:
        1. Initializes WASAPI stream with loopback device
        2. Verifies stream configuration
        3. Monitors stream health
        
        Test Sequence:
            1. Get loopback device configuration
            2. Initialize WASAPI stream
            3. Verify stream properties
            4. Check stream activity
            5. Log performance metrics
        
        Expected Results:
            - Stream initialization successful
            - Stream properly configured
            - Stream remains active
            - Metrics properly logged
        
        Example Metrics:
            - device_name: Loopback device name
            - sample_rate: Audio sample rate
            - channels: Number of channels
            - latency: Expected device latency
        """
        try:
            loopback_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
        except ValueError:
            self.skipTest("No loopback device available")
            
        wasapi = WASAPIMonitor(self.coordinator)
        
        # Initialize stream with system loopback device
        success = wasapi.initialize_stream(device_index=loopback_config.device_index)
        self.assertTrue(success, f"Failed to initialize stream with {loopback_config.name}")
        
        # Verify stream configuration
        self.assertTrue(hasattr(wasapi, 'stream'), "No stream created")
        self.assertTrue(wasapi.stream.is_active(), "Stream not active")
        
        # Log stream metrics
        self.log_metric("loopback_capture", {
            'device_name': loopback_config.name,
            'sample_rate': loopback_config.sample_rate,
            'channels': loopback_config.channels,
            'latency': loopback_config.expected_latency
        })
        
        # Clean up
        wasapi.cleanup()
        
    @pytest.mark.slow
    def test_vb_cable_capture(self):
        """Test VB-Cable audio capture.
        
        Verifies the system's ability to capture audio through the
        VB-Cable virtual audio device. This test:
        1. Initializes WASAPI stream with VB-Cable
        2. Verifies stream configuration
        3. Monitors stream health
        
        Test Sequence:
            1. Get VB-Cable device configuration
            2. Initialize WASAPI stream
            3. Verify stream properties
            4. Check stream activity
            5. Log performance metrics
        
        Expected Results:
            - Stream initialization successful
            - Stream properly configured
            - Stream remains active
            - Metrics properly logged
        
        Example Metrics:
            - device_name: VB-Cable device name
            - sample_rate: Audio sample rate
            - channels: Number of channels
            - latency: Expected device latency
        """
        try:
            vb_config = self.device_manager.get_config(DeviceType.VB_CABLE)
        except ValueError:
            self.skipTest("No VB-Cable device available")
            
        wasapi = WASAPIMonitor(self.coordinator)
        
        # Initialize stream with VB-Cable device
        success = wasapi.initialize_stream(device_index=vb_config.device_index)
        self.assertTrue(success, f"Failed to initialize stream with {vb_config.name}")
        
        # Verify stream configuration
        self.assertTrue(hasattr(wasapi, 'stream'), "No stream created")
        self.assertTrue(wasapi.stream.is_active(), "Stream not active")
        
        # Log stream metrics
        self.log_metric("vb_cable_capture", {
            'device_name': vb_config.name,
            'sample_rate': vb_config.sample_rate,
            'channels': vb_config.channels,
            'latency': vb_config.expected_latency
        })
        
        # Clean up
        wasapi.cleanup()
        
    @pytest.mark.slow
    def test_device_switching(self):
        """Test switching between audio devices.
        
        Verifies the system's ability to handle device switching
        scenarios smoothly. This test:
        1. Generates various switching scenarios
        2. Tests each switching combination
        3. Verifies stream health after switches
        
        Test Sequence:
            1. Generate switch scenarios
            2. Initialize with primary device
            3. Switch to secondary device
            4. Verify stream health
            5. Allow stabilization time
        
        Expected Results:
            - All switches successful
            - Stream health maintained
            - No resource leaks
            - Performance metrics logged
        
        Example Metrics:
            - primary_device: Initial device name
            - secondary_device: Target device name
            - duration: Scenario duration
            - recovery_time: Switch recovery time
        """
        # Generate device switch scenarios
        scenarios = self.scenario_generator.generate_device_switch_scenarios()
        if not scenarios:
            self.skipTest("No valid device switch scenarios available")
            
        wasapi = WASAPIMonitor(self.coordinator)
        
        for scenario in scenarios:
            # Log scenario details
            self.log_metric(f"switch_scenario_{scenario.scenario_type.name}", {
                'primary_device': scenario.primary_device.name,
                'secondary_device': scenario.secondary_device.name,
                'duration': scenario.duration,
                'recovery_time': scenario.expected_recovery_time
            })
            
            # Test the switch
            success = wasapi.initialize_stream(
                device_index=scenario.primary_device.device_index
            )
            self.assertTrue(success, f"Failed to initialize {scenario.primary_device.name}")
            
            # Switch to secondary device
            success = wasapi.initialize_stream(
                device_index=scenario.secondary_device.device_index
            )
            self.assertTrue(success, f"Failed to switch to {scenario.secondary_device.name}")
            
            # Verify stream health
            state = wasapi.coordinator.get_state()
            self.assertTrue(state.stream_health, "Stream health check failed after switch")
            
            # Allow time for stability
            time.sleep(0.5)
            
        # Clean up
        wasapi.cleanup()
        
    @pytest.mark.slow
    def test_concurrent_capture(self):
        """Test capturing from both devices concurrently.
        
        Verifies the system's ability to capture audio from multiple
        devices simultaneously. This test:
        1. Initializes streams for both devices
        2. Verifies concurrent operation
        3. Monitors performance impact
        
        Test Sequence:
            1. Initialize system loopback stream
            2. Initialize VB-Cable stream
            3. Verify both streams active
            4. Monitor concurrent performance
            5. Check resource usage
        
        Expected Results:
            - Both streams initialize
            - Both streams remain active
            - System remains stable
            - Performance within limits
        
        Example Metrics:
            - system_device: System device name
            - vb_cable_device: VB-Cable device name
            - system_latency: System stream latency
            - vb_cable_latency: VB-Cable stream latency
        """
        try:
            loopback_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
            vb_config = self.device_manager.get_config(DeviceType.VB_CABLE)
        except ValueError:
            self.skipTest("Required test devices not available")
            
        system_monitor = WASAPIMonitor(self.coordinator)
        vb_cable_monitor = WASAPIMonitor(self.coordinator)
        
        # Initialize both streams
        system_success = system_monitor.initialize_stream(
            device_index=loopback_config.device_index
        )
        vb_cable_success = vb_cable_monitor.initialize_stream(
            device_index=vb_config.device_index
        )
        
        self.assertTrue(system_success, f"Failed to initialize {loopback_config.name}")
        self.assertTrue(vb_cable_success, f"Failed to initialize {vb_config.name}")
        
        # Verify both streams
        self.assertTrue(system_monitor.stream.is_active(), "System stream not active")
        self.assertTrue(vb_cable_monitor.stream.is_active(), "VB-Cable stream not active")
        
        # Log concurrent capture metrics
        self.log_metric("concurrent_capture", {
            'system_device': loopback_config.name,
            'vb_cable_device': vb_config.name,
            'system_latency': loopback_config.expected_latency,
            'vb_cable_latency': vb_config.expected_latency
        })
        
        # Clean up
        system_monitor.cleanup()
        vb_cable_monitor.cleanup()
        
    @pytest.mark.slow
    def test_stream_recovery(self):
        """Test stream recovery after interruption.
        
        Verifies the system's ability to recover from various stream
        interruption scenarios. This test:
        1. Tests basic failure scenarios
        2. Tests concurrent failures
        3. Tests cascading failures
        4. Verifies recovery mechanisms
        
        Test Sequence:
            1. Generate failure scenarios
            2. Initialize test stream
            3. Apply error sequences
            4. Monitor recovery attempts
            5. Verify successful recovery
        
        Expected Results:
            - Recovery within time limits
            - Proper error handling
            - Stream health restored
            - Recovery metrics logged
        
        Example Metrics:
            - device: Device under test
            - duration: Test duration
            - recovery_time: Time to recover
            - error_count: Number of errors
        """
        # Generate failure scenarios
        scenarios = []
        scenarios.extend(self.scenario_generator.generate_basic_scenarios())
        scenarios.extend(self.scenario_generator.generate_concurrent_failure_scenarios())
        scenarios.extend(self.scenario_generator.generate_cascading_failure_scenarios())
        
        if not scenarios:
            self.skipTest("No valid failure scenarios available")
            
        wasapi = WASAPIMonitor(self.coordinator)
        
        for scenario in scenarios:
            # Log scenario details
            self.log_metric(f"recovery_scenario_{scenario.scenario_type.name}", {
                'device': scenario.primary_device.name,
                'duration': scenario.duration,
                'recovery_time': scenario.expected_recovery_time,
                'error_count': len(scenario.error_sequence)
            })
            
            # Initialize stream
            success = wasapi.initialize_stream(
                device_index=scenario.primary_device.device_index
            )
            self.assertTrue(success, f"Failed to initialize {scenario.primary_device.name}")
            
            # Apply error sequence
            for error in scenario.error_sequence:
                wasapi.coordinator.update_state(stream_health=False)
                time.sleep(0.1)  # Allow time for error to register
                
                # Wait for recovery
                recovery_start = time.time()
                while not wasapi.coordinator.get_state().stream_health:
                    if time.time() - recovery_start > scenario.expected_recovery_time:
                        self.fail(f"Recovery timeout for {error['error_type']}")
                    time.sleep(0.1)
                
                # Log recovery metrics
                recovery_time = time.time() - recovery_start
                self.log_metric(f"recovery_time_{error['error_type']}", recovery_time)
            
            # Clean up before next scenario
            wasapi.cleanup()
            time.sleep(0.5)  # Allow time between scenarios
        
    @pytest.mark.slow
    def test_buffer_handling(self):
        """Test audio buffer handling with real data.
        
        Verifies the system's buffer management capabilities with
        real audio data. This test:
        1. Captures real audio data
        2. Monitors buffer statistics
        3. Verifies buffer performance
        
        Test Sequence:
            1. Initialize audio stream
            2. Capture real audio data
            3. Monitor buffer statistics
            4. Verify queue size
            5. Check performance stats
        
        Expected Results:
            - Buffer properly initialized
            - Data successfully captured
            - Queue size maintained
            - Performance stats logged
        
        Example Metrics:
            - capture_queue_size: Buffer queue length
            - buffer_stats: Detailed performance stats
        """
        try:
            loopback_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
        except ValueError:
            self.skipTest("No loopback device available")
            
        wasapi = WASAPIMonitor(self.coordinator)
        
        # Initialize stream
        success = wasapi.initialize_stream(device_index=loopback_config.device_index)
        self.assertTrue(success, f"Failed to initialize {loopback_config.name}")
        
        # Wait for some audio data
        time.sleep(1.0)
        
        # Check buffer stats
        buffer_stats = wasapi.buffer_manager.get_performance_stats()
        self.assertGreater(buffer_stats['capture_queue_size'], 0)
        
        # Log buffer metrics
        self.log_metric("buffer_stats", buffer_stats)
        
        # Clean up
        wasapi.cleanup()
        
    @pytest.mark.slow
    def test_adaptive_performance(self):
        """Test adaptive performance under real conditions.
        
        Verifies the system's ability to adapt performance parameters
        based on real-world conditions. This test:
        1. Monitors system performance
        2. Verifies adaptive behaviors
        3. Tracks resource usage
        
        Test Sequence:
            1. Start adaptive capture
            2. Allow adaptation period
            3. Collect performance stats
            4. Verify adaptations
            5. Monitor resource usage
        
        Expected Results:
            - Capture starts successfully
            - System adapts to conditions
            - Performance stats collected
            - Resource usage optimized
        
        Example Metrics:
            - cpu_usage: CPU utilization
            - buffer_size: Adapted buffer size
            - adaptive_performance: Overall stats
        """
        try:
            loopback_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
        except ValueError:
            self.skipTest("No loopback device available")
            
        capture = AdaptiveAudioCapture(self.coordinator)
        
        # Start capture
        success = capture.start_capture()
        self.assertTrue(success, "Failed to start adaptive capture")
        
        # Let it run and adapt
        time.sleep(2.0)
        
        # Get performance stats
        stats = capture.get_performance_stats()
        
        # Verify stats
        self.assertIsNotNone(stats['cpu_usage'], "No CPU usage data")
        self.assertIsNotNone(stats['buffer_size'], "No buffer size data")
        
        # Log performance metrics
        self.log_metric("adaptive_performance", stats)
        
        # Stop capture
        capture.stop_capture()
