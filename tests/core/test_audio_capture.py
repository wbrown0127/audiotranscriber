"""
COMPONENT_NOTES:
{
    "name": "TestAudioCapture",
    "type": "Test Suite",
    "description": "Core test suite for verifying audio capture functionality, including adaptive capture, performance monitoring, and WASAPI integration",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TAC[TestAudioCapture] --> AAC[AdaptiveAudioCapture]
                TAC --> MC[MonitoringCoordinator]
                TAC --> BM[BufferManager]
                TAC --> DM[DeviceManager]
                TAC --> WI[WASAPIInterface]
                TAC --> CT[ComponentTest]
        ```",
        "dependencies": {
            "AdaptiveAudioCapture": "Main component under test",
            "MonitoringCoordinator": "Provides system monitoring",
            "BufferManager": "Manages audio buffers",
            "DeviceManager": "Audio device configuration",
            "WASAPIInterface": "Windows audio API integration",
            "ComponentTest": "Base test functionality"
        }
    },
    "notes": [
        "Tests performance monitoring and statistics collection",
        "Verifies buffer size adjustment based on system load",
        "Tests WASAPI stream recovery mechanism",
        "Validates device switching capabilities",
        "Handles both real and mock audio devices"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_audio_capture.py",
            "python -m pytest tests/core/test_audio_capture.py -k test_performance_monitoring"
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
            "os": "Windows (for WASAPI)",
            "audio": "Audio devices or virtual cables",
            "memory": "500MB minimum"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Moderate CPU usage during capture",
            "Audio device access required",
            "Proper cleanup of audio resources"
        ]
    }
}
"""
import asyncio
import pytest
import logging
import pyaudiowpatch as pyaudio
from unittest.mock import Mock, patch
from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.buffer_manager import BufferManager
from tests.utilities.base import ComponentTest
from audio_transcriber.test_config.device_config import DeviceManager, DeviceType

class TestAudioCapture(ComponentTest):
    async def asyncSetUp(self):
        """Set up test environment."""
        self.logger = logging.getLogger(self.__class__.__name__)
        
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
            
            # Try to get real devices, fall back to mock if unavailable
            try:
                self.has_real_devices = (
                    self.device_manager.validate_device(DeviceType.SYSTEM_LOOPBACK) or
                    self.device_manager.validate_device(DeviceType.VB_CABLE)
                )
                if self.has_real_devices:
                    self.logger.info("Using real audio devices")
                    
            except Exception as e:
                self.logger.warning(f"Error validating real devices: {e}")
                self.has_real_devices = False
                
            if not self.has_real_devices:
                self.logger.info("Using mock audio devices")
                # Set up mock devices
                self.mock_device = Mock()
                self.mock_device.device_index = 0
                self.mock_device.name = "Mock Audio Device"
                self.mock_device.channels = 2
                self.mock_device.sample_rate = 44100
                self.mock_device.expected_latency = 0.1
                
                # Patch device manager to return mock device
                self.device_manager.get_config = Mock(return_value=self.mock_device)
                self.device_manager.validate_device = Mock(return_value=True)
                
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
        """Clean up test environment."""
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
    async def test_performance_monitoring(self):
        """Test performance monitoring and statistics collection."""
        try:
            stats = self.capture.get_performance_stats()
            
            # Verify required metrics are present
            self.assertIn('cpu_usage', stats)
            self.assertIn('temperature', stats)
            self.assertIn('stream_health', stats)
            
            # Verify metric ranges
            self.assertGreaterEqual(stats['cpu_usage'], 0)
            self.assertLess(stats['cpu_usage'], 100)
            self.assertGreaterEqual(stats['temperature'], 0)
            self.assertIsInstance(stats['stream_health'], bool)
            
            # Log metrics for analysis
            for key, value in stats.items():
                self.log_metric(f"capture_{key}", value)
                
        except Exception as e:
            self.logger.error(f"Performance monitoring test failed: {e}")
            raise
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_buffer_adjustment(self):
        """Test buffer size adjustment based on system load."""
        try:
            # Track initial resource state
            initial_metrics = await self.coordinator.get_resource_metrics()
            
            monitor = self.capture.monitor
            initial_size = monitor.buffer_sizes[0]
            
            # Start capture
            self.capture.start_capture()
            
            # Use shorter stabilization time
            await asyncio.sleep(0.5)
            
            # Get CPU stats
            cpu_load, temp = monitor.get_cpu_stats()
            monitor.reset_cooldown()
            
            # Test adjustment
            should_adjust = monitor.should_adjust(cpu_load, temp)
            if should_adjust:
                new_size = monitor.adjust_buffer_size()
                self.assertNotEqual(new_size, initial_size)
                self.assertGreater(new_size, 0)
                self.assertLess(new_size, 1024 * 1024)  # Reasonable max size
            
            # Verify no resource leaks during adjustment
            current_metrics = await self.coordinator.get_resource_metrics()
            self.assertEqual(
                initial_metrics['allocated'],
                current_metrics['allocated'],
                "Resource leak detected during buffer adjustment"
            )
            
            # Log metrics
            self.log_metric("initial_buffer_size", initial_size)
            self.log_metric("cpu_load", cpu_load)
            self.log_metric("temperature", temp)
            self.log_metric("resource_allocated", current_metrics['allocated'])
            
        except Exception as e:
            self.logger.error(f"Buffer adjustment test failed: {e}")
            raise
        finally:
            # Ensure capture is stopped
            self.capture.stop_capture()
        
    @pytest.mark.fast
    @pytest.mark.asyncio  # Note: Required for real-time audio streaming
    async def test_wasapi_recovery(self):
        """Test WASAPI stream recovery mechanism."""
        try:
            if not self.has_real_devices:
                # Use mock device
                device_config = self.mock_device
                self.logger.info("Using mock device for WASAPI test")
            else:
                try:
                    device_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
                    self.logger.info(f"Using real device: {device_config.name}")
                except ValueError as e:
                    self.logger.warning("No loopback device available")
                    self.skipTest("No loopback device available")
            
            # Initialize stream
            success = await self.capture.wasapi.initialize_stream(
                device_index=device_config.device_index
            )
            self.assertTrue(success, f"Failed to initialize stream with device {device_config.name}")
            
            # Start capture with shorter stabilization time
            await self.capture.start_capture()
            await asyncio.sleep(0.5)  # Allow time for real-time streaming setup
            
            # Get stream metrics through coordinator
            stream_metrics = await self.coordinator.get_stream_metrics()
            self.log_metric("initial_stream_health", stream_metrics['health'])
            
            # Simulate stream interruption and verify recovery
            await self.capture.wasapi.simulate_interruption()
            await asyncio.sleep(0.2)  # Allow time for recovery
            
            # Verify recovery
            recovery_metrics = await self.coordinator.get_stream_metrics()
            self.assertTrue(
                recovery_metrics['health'],
                f"Stream recovery failed for device {device_config.name}"
            )
            
            # Log metrics
            self.log_metric("recovery_time", recovery_metrics['recovery_time'])
            self.log_metric("stream_health", recovery_metrics['health'])
            self.log_metric("device_name", device_config.name)
            self.log_metric("device_channels", device_config.channels)
            self.log_metric("device_sample_rate", device_config.sample_rate)
            
        except Exception as e:
            self.logger.error(f"WASAPI recovery test failed: {e}")
            raise
        finally:
            # Ensure cleanup
            self.capture.stop_capture()
        
    @pytest.mark.fast
    @pytest.mark.asyncio  # Note: Required for real-time audio streaming
    async def test_device_switching(self):
        """Test switching between audio devices."""
        try:
            if not self.has_real_devices:
                self.logger.info("Using mock devices for switching test")
                # Create two mock devices
                mock_devices = [
                    Mock(
                        device_index=i,
                        name=f"Mock Device {i}",
                        channels=2,
                        sample_rate=44100,
                        expected_latency=0.1
                    ) for i in range(2)
                ]
                devices_to_test = mock_devices
            else:
                try:
                    self.logger.info("Using real devices for switching test")
                    loopback_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
                    vb_config = self.device_manager.get_config(DeviceType.VB_CABLE)
                    devices_to_test = [loopback_config, vb_config]
                except ValueError as e:
                    self.logger.warning("Required test devices not available")
                    self.skipTest("Required test devices not available")
            
            for device in devices_to_test:
                try:
                    self.logger.info(f"Testing device: {device.name}")
                    
                    # Initialize stream with async handling
                    success = await self.capture.wasapi.initialize_stream(
                        device_index=device.device_index
                    )
                    self.assertTrue(
                        success,
                        f"Failed to initialize stream with device {device.name}"
                    )
                    
                    # Start capture with real-time streaming setup
                    await self.capture.start_capture()
                    await asyncio.sleep(0.5)  # Allow time for streaming setup
                    
                    # Get stream metrics through coordinator
                    stream_metrics = await self.coordinator.get_stream_metrics()
                    self.assertTrue(
                        stream_metrics['health'],
                        f"Stream health check failed for device {device.name}"
                    )
                    
                    # Verify real-time streaming
                    buffer_stats = await self.capture.get_buffer_stats()
                    self.assertGreater(
                        buffer_stats['processed_frames'],
                        0,
                        f"No audio frames processed for device {device.name}"
                    )
                    
                    # Log metrics
                    self.log_metric(f"{device.name}_health", stream_metrics['health'])
                    self.log_metric(f"{device.name}_latency", device.expected_latency)
                    self.log_metric(f"{device.name}_processed_frames", buffer_stats['processed_frames'])
                    
                except Exception as e:
                    self.logger.error(f"Error testing device {device.name}: {e}")
                    raise
                finally:
                    # Ensure cleanup between devices
                    self.capture.stop_capture()
                    await asyncio.sleep(0.2)
                    
        except Exception as e:
            self.logger.error(f"Device switching test failed: {e}")
            raise

if __name__ == '__main__':
    unittest.main()
