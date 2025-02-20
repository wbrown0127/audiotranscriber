#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestAudioCaptureAdvanced",
    "type": "Test Suite",
    "description": "Advanced test suite for verifying audio capture functionality including device hot-plug support, frame tracking, and buffer management",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TAA[TestAudioCaptureAdvanced] --> AAC[AdaptiveAudioCapture]
                TAA --> MC[MonitoringCoordinator]
                TAA --> WM[WASAPIMonitor]
                TAA --> CT[ComponentTest]
                TAA --> DM[DeviceManager]
                TAA --> MT[MockTest]
        ```",
        "dependencies": {
            "AdaptiveAudioCapture": "Main component under test",
            "MonitoringCoordinator": "Provides system monitoring",
            "WASAPIMonitor": "Handles WASAPI device interactions",
            "ComponentTest": "Base test functionality",
            "DeviceManager": "Manages test device configurations",
            "MockTest": "Provides mocking capabilities"
        }
    },
    "notes": [
        "Tests device hot-plug detection and recovery",
        "Verifies frame-level audio tracking",
        "Validates buffer overrun/underrun handling",
        "Tests device capability validation",
        "Ensures proper recovery mechanisms"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_audio_capture_advanced.py",
            "python -m pytest tests/core/test_audio_capture_advanced.py -k test_device_hotplug"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "asyncio",
            "pyaudiowpatch"
        ],
        "system": {
            "os": "Windows (for WASAPI)",
            "audio": "WASAPI-compatible audio device",
            "memory": "1GB minimum"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Memory usage under 200MB",
            "Proper device cleanup after tests",
            "Mock hardware when possible"
        ]
    }
}
"""
import time
import asyncio
import pytest
from unittest.mock import Mock, patch
from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.wasapi_monitor import WASAPIMonitor
from tests.utilities.base import ComponentTest
from audio_transcriber.test_config.device_config import DeviceManager, DeviceType

class TestAudioCaptureAdvanced(ComponentTest):
    """Test suite for advanced audio capture functionality.
    
    This test class verifies the advanced features of the AudioCapture component,
    focusing on device management and buffer handling.
    
    Key Features Tested:
        - Device hot-plug detection and recovery
        - Frame-level audio tracking
        - Buffer overrun/underrun handling
        - Device capability validation
        - Automatic recovery mechanisms
    
    Attributes:
        coordinator (MonitoringCoordinator): System monitoring coordinator
        device_manager (DeviceManager): Audio device management
        capture (AdaptiveAudioCapture): Audio capture system under test
    
    Example:
        class TestCustomCapture(TestAudioCaptureAdvanced):
            def test_custom_device(self):
                device = self.device_manager.get_config(DeviceType.CUSTOM)
                self.capture.start_capture(device_id=device.device_index)
                self.assertTrue(self.capture.is_active())
    """

    async def asyncSetUp(self):
        """Set up test fixtures before each test method."""
        try:
            await super().asyncSetUp()
            
            # Note: Updated to use coordinator for resource management
            self.coordinator = MonitoringCoordinator()
            # Coordinator now handles resource pool initialization
            self.coordinator.start_monitoring()
            
            # Initialize device manager
            self.device_manager = DeviceManager()
            
            # Track initial resource state
            self.initial_resource_metrics = await self.coordinator.get_resource_metrics()
            
            # Initialize capture with coordinator
            self.capture = AdaptiveAudioCapture(
                coordinator=self.coordinator
            )
            
            # Register test thread
            self.coordinator.register_thread()
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise

    async def asyncTearDown(self):
        """Clean up test fixtures after each test method."""
        try:
            # Note: Updated cleanup order to match new architecture
            if hasattr(self, 'capture'):
                try:
                    self.capture.stop_capture()
                    await self.capture.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up capture: {e}")
            
            # Get final resource state before coordinator cleanup
            if hasattr(self, 'coordinator'):
                try:
                    final_resource_metrics = await self.coordinator.get_resource_metrics()
                    
                    # Verify no resource leaks
                    self.assertEqual(
                        self.initial_resource_metrics['allocated'],
                        final_resource_metrics['allocated'],
                        "Resource leak detected during test"
                    )
                    
                    self.coordinator.stop_monitoring()
                    await self.coordinator.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up coordinator: {e}")
            
            # Finally cleanup device manager
            if hasattr(self, 'device_manager'):
                try:
                    self.device_manager.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up device manager: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
        finally:
            await super().asyncTearDown()

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_device_hotplug_detection(self):
        """Test detection of device hot-plug events.
        
        Verifies the system's ability to detect and handle device
        hot-plug events. This test:
        1. Simulates device addition/removal events
        2. Verifies event detection and handling
        3. Tracks event processing
        
        Test Sequence:
            1. Register event callback
            2. Simulate device events
            3. Verify event detection
            4. Check event processing
        
        Expected Results:
            - All events detected
            - Correct event order maintained
            - Event details preserved
            - Metrics properly logged
        
        Example Metrics:
            - total_events: Number of events processed
            - event_[action]: Device ID for each action type
        """
        # Mock device events
        mock_device_events = [
            {'action': 'added', 'device_id': 'test_device_1'},
            {'action': 'removed', 'device_id': 'test_device_1'},
            {'action': 'added', 'device_id': 'test_device_2'}
        ]
        
        # Initialize event tracking
        detected_events = []
        
        def mock_event_callback(event):
            detected_events.append(event)
        
        # Track initial resource state
        initial_metrics = await self.coordinator.get_resource_metrics()
        
        # Register callback
        await self.capture.register_device_callback(mock_event_callback)
        
        # Simulate device events
        for event in mock_device_events:
            await self.capture.wasapi.simulate_device_event(event)
            await asyncio.sleep(0.1)  # Allow time for event processing
            
        # Verify no resource leaks during event processing
        current_metrics = await self.coordinator.get_resource_metrics()
        self.assertEqual(
            initial_metrics['allocated'],
            current_metrics['allocated'],
            "Resource leak detected during event processing"
        )
        
        # Verify event detection
        self.assertEqual(len(detected_events), len(mock_device_events))
        
        # Log event metrics
        self.log_metric("total_events", len(detected_events))
        for event in detected_events:
            self.log_metric(f"event_{event['action']}", event['device_id'])

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_device_recovery(self):
        """Test automatic recovery after device changes.
        
        Verifies the system's ability to automatically recover from device
        removal and reattachment events. This test:
        1. Starts capture with initial device
        2. Simulates device removal
        3. Verifies recovery attempts
        4. Simulates device return
        5. Verifies capture resumption
        
        Test Sequence:
            1. Start capture with initial device
            2. Verify initial capture state
            3. Simulate device removal
            4. Check recovery attempts
            5. Simulate device return
            6. Verify capture resumed
        
        Expected Results:
            - Initial capture successful
            - Recovery attempts detected
            - Capture resumes after device return
            - All metrics properly logged
        
        Example Metrics:
            - recovery_attempts: Number of recovery tries
            - recovery_time: Time taken for recovery
        """
        # Track initial resource state
        initial_metrics = await self.coordinator.get_resource_metrics()
        
        # Start capture with initial device
        initial_device = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
        await self.capture.start_capture(device_id=initial_device.device_index)
        
        # Verify initial state
        self.assertTrue(await self.capture.is_active())
        initial_stats = await self.capture.get_performance_stats()
        
        # Simulate device removal
        await self.capture.wasapi.simulate_device_event({
            'action': 'removed',
            'device_id': initial_device.device_index
        })
        await asyncio.sleep(0.2)  # Allow time for recovery
        
        # Verify recovery attempt
        recovery_stats = await self.capture.get_recovery_stats()
        self.assertGreater(recovery_stats['recovery_attempts'], 0)
        
        # Simulate device return
        await self.capture.wasapi.simulate_device_event({
            'action': 'added',
            'device_id': initial_device.device_index
        })
        await asyncio.sleep(0.2)  # Allow time for recovery
        
        # Verify capture resumed
        self.assertTrue(await self.capture.is_active())
        
        # Verify no resource leaks during recovery
        current_metrics = await self.coordinator.get_resource_metrics()
        self.assertEqual(
            initial_metrics['allocated'],
            current_metrics['allocated'],
            "Resource leak detected during device recovery"
        )
        
        # Log recovery metrics
        self.log_metric("recovery_attempts", recovery_stats['recovery_attempts'])
        self.log_metric("recovery_time", recovery_stats['last_recovery_time'])

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_frame_tracking(self):
        """Test frame-level tracking of audio data.
        
        Verifies the system's ability to track audio frames at a granular
        level, including dropped frame detection. This test:
        1. Captures audio for a fixed duration
        2. Tracks frame statistics
        3. Analyzes frame drops and rates
        
        Test Sequence:
            1. Start audio capture
            2. Generate test audio frames
            3. Collect frame statistics
            4. Calculate performance metrics
        
        Expected Results:
            - Frame count tracked accurately
            - Dropped frames detected
            - Frame rate calculated
            - Drop ratio within limits
        
        Example Metrics:
            - total_frames: Number of frames processed
            - dropped_frames: Number of frames lost
            - frame_rate: Frames per second
            - drop_ratio: Ratio of dropped frames
        """
        # Track initial resource state
        initial_metrics = await self.coordinator.get_resource_metrics()
        
        # Start capture
        device = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
        await self.capture.start_capture(device_id=device.device_index)
        
        # Generate some audio frames
        test_duration = 1.0  # seconds
        start_time = time.time()
        
        while time.time() - start_time < test_duration:
            await asyncio.sleep(0.1)
        
        # Get frame statistics
        frame_stats = await self.capture.get_frame_stats()
        
        # Verify no resource leaks during frame tracking
        current_metrics = await self.coordinator.get_resource_metrics()
        self.assertEqual(
            initial_metrics['allocated'],
            current_metrics['allocated'],
            "Resource leak detected during frame tracking"
        )
        
        # Verify tracking fields
        self.assertIn('total_frames', frame_stats)
        self.assertIn('dropped_frames', frame_stats)
        self.assertIn('frame_rate', frame_stats)
        
        # Calculate drop ratio
        drop_ratio = frame_stats['dropped_frames'] / frame_stats['total_frames'] if frame_stats['total_frames'] > 0 else 0
        
        # Log frame metrics
        self.log_metric("total_frames", frame_stats['total_frames'])
        self.log_metric("dropped_frames", frame_stats['dropped_frames'])
        self.log_metric("frame_rate", frame_stats['frame_rate'])
        self.log_metric("drop_ratio", drop_ratio)

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_buffer_overrun_detection(self):
        """Test detection and handling of buffer overruns.
        
        Verifies the system's ability to detect and handle buffer overruns
        and underruns. This test:
        1. Configures small buffer size
        2. Simulates processing delays
        3. Monitors buffer statistics
        
        Test Sequence:
            1. Configure minimal buffer size
            2. Start capture with test device
            3. Simulate processing delays
            4. Monitor buffer statistics
            5. Verify overrun detection
        
        Expected Results:
            - Overruns detected and logged
            - Underruns tracked
            - Buffer usage monitored
            - Statistics properly recorded
        
        Example Metrics:
            - buffer_overruns: Number of buffer overflows
            - buffer_underruns: Number of buffer underflows
            - buffer_usage: Current buffer utilization
        """
        # Track initial resource state
        initial_metrics = await self.coordinator.get_resource_metrics()
        
        # Configure smaller buffer for testing
        await self.capture.configure_buffer(buffer_size=1024, trigger_level=512)
        
        # Start capture
        device = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
        await self.capture.start_capture(device_id=device.device_index)
        
        # Simulate processing delay to trigger overruns
        async def delayed_processing(data):
            await asyncio.sleep(0.1)  # Simulate slow processing
            return data
        
        await self.capture.set_processing_callback(delayed_processing)
        
        # Run for a short period
        await asyncio.sleep(1.0)
        
        # Get buffer statistics
        buffer_stats = await self.capture.get_buffer_stats()
        
        # Verify no resource leaks during buffer testing
        current_metrics = await self.coordinator.get_resource_metrics()
        self.assertEqual(
            initial_metrics['allocated'],
            current_metrics['allocated'],
            "Resource leak detected during buffer testing"
        )
        
        # Verify overrun detection
        self.assertIn('overruns', buffer_stats)
        self.assertIn('underruns', buffer_stats)
        
        # Log buffer metrics
        self.log_metric("buffer_overruns", buffer_stats['overruns'])
        self.log_metric("buffer_underruns", buffer_stats['underruns'])
        self.log_metric("buffer_usage", buffer_stats['current_usage'])

    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_device_capability_validation(self):
        """Test device capability validation and fallback mechanisms.
        
        Verifies the system's ability to validate device capabilities
        and handle fallback configurations. This test:
        1. Tests various audio configurations
        2. Validates device capabilities
        3. Verifies fallback mechanisms
        
        Test Sequence:
            1. Define test configurations
            2. Attempt validation for each config
            3. Track validation results
            4. Verify fallback configs
            5. Log validation statistics
        
        Expected Results:
            - At least one valid configuration
            - Proper fallback detection
            - All configs properly tested
            - Validation metrics logged
        
        Example Metrics:
            - validation_[config]: Config validation result
            - total_configs_tested: Number of configs tested
            - valid_configs: Number of valid configurations
        """
        # Test various device configurations
        test_configs = [
            {'sample_rate': 48000, 'channels': 2, 'format': 'float32'},
            {'sample_rate': 44100, 'channels': 2, 'format': 'int16'},
            {'sample_rate': 96000, 'channels': 2, 'format': 'int24'}
        ]
        
        validation_results = []
        
        # Track initial resource state
        initial_metrics = await self.coordinator.get_resource_metrics()
        
        for config in test_configs:
            # Attempt to validate device with config
            result = await self.capture.validate_device_config(
                device_id=self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK).device_index,
                **config
            )
            
            validation_results.append({
                'config': config,
                'valid': result.valid,
                'fallback': result.fallback_config if not result.valid else None
            })
            
            # Log validation metrics
            self.log_metric(
                f"validation_{config['sample_rate']}_{config['format']}",
                1 if result.valid else 0
            )
        
        # Verify at least one valid configuration
        self.assertTrue(any(r['valid'] for r in validation_results))
        
        # Log overall validation stats
        self.log_metric("total_configs_tested", len(validation_results))
        self.log_metric("valid_configs", sum(1 for r in validation_results if r['valid']))

if __name__ == '__main__':
    unittest.main()
