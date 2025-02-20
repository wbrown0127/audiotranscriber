"""
Test Updates [2025-02-19]:
- Converted to async patterns for continuous signal processing
- Added ResourcePool injection through MonitoringCoordinator
- Implemented proper lock ordering
- Added tier-aware buffer optimization tests
- Added comprehensive error context and validation
- Updated for Python 3.13.1 compatibility

COMPONENT_NOTES:
{
    "name": "TestSignalProcessor",
    "type": "Test Suite",
    "description": "Core test suite for verifying signal processing functionality, including audio processing, memory management, and fallback operations",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TSP[TestSignalProcessor] --> SP[SignalProcessor]
                TSP --> MC[MonitoringCoordinator]
                TSP --> CT[ComponentTest]
                SP --> AP[AudioProcessor]
                SP --> MM[MemoryManager]
                SP --> FB[FallbackProcessor]
        ```",
        "dependencies": {
            "SignalProcessor": "Main component under test",
            "MonitoringCoordinator": "System monitoring",
            "ComponentTest": "Base test functionality",
            "AudioProcessor": "Signal processing operations",
            "MemoryManager": "Memory threshold monitoring",
            "FallbackProcessor": "Emergency processing mode"
        }
    },
    "notes": [
        "Tests memory threshold monitoring and cleanup",
        "Verifies core audio signal processing",
        "Tests emergency fallback processing mode",
        "Validates signal quality measurements",
        "Ensures proper memory management",
        "Monitors processing performance"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_signal_processor.py",
            "python -m pytest tests/core/test_signal_processor.py -k test_audio_processing"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "numpy",
            "threading"
        ],
        "system": {
            "memory": "100MB minimum",
            "cpu": "Support for audio processing"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Moderate memory usage for audio buffers",
            "CPU intensive during signal processing",
            "Proper cleanup after tests"
        ]
    }
}
"""
import numpy as np
import pytest
import asyncio
import logging
import threading
from audio_transcriber.signal_processor import SignalProcessor
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.resource_pool import PoolTier
from tests.utilities.base import ComponentTest

@pytest.mark.asyncio  # Mark all tests in class as async
class TestSignalProcessor(ComponentTest):
    async def asyncSetUp(self):
        """Set up test environment."""
        await super().setUp()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize coordinator with proper setup and resource management
        self.coordinator = MonitoringCoordinator()
        await self.coordinator.start_monitoring()
        
        # Initialize signal processor with coordinator for resource management
        self.processor = SignalProcessor(self.coordinator)
        await self.coordinator.register_component(self.processor)
        
        # Configure signal processor with tier-aware settings
        await self.processor.configure({
            'sample_rate': 48000,
            'channels': 2,
            'width': 2,
            'memory_threshold': 1024 * 1024 * 100,  # 100MB
            'tier_sizes': {
                PoolTier.SMALL: 4 * 1024,    # 4KB
                PoolTier.MEDIUM: 64 * 1024,  # 64KB
                PoolTier.LARGE: 1024 * 1024  # 1MB
            }
        })
        
    async def asyncTearDown(self):
        """Clean up test environment."""
        try:
            # Follow proper lock ordering during cleanup
            if hasattr(self, 'processor'):
                await self.coordinator.unregister_component(self.processor)
                await self.processor.cleanup()
            
            if hasattr(self, 'coordinator'):
                # Ensure proper resource cleanup
                await self.coordinator.stop_monitoring()
                await self.coordinator.cleanup_resources()
                await self.coordinator.request_shutdown()
                
                # Verify all resources are properly released
                stats = await self.coordinator.get_resource_stats()
                assert stats['active_buffers'] == 0, "Resource leak detected"
                
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}", exc_info=True)
            raise
        finally:
            await super().tearDown()
        
    @pytest.mark.fast
    async def test_memory_management(self):
        """Test memory threshold monitoring and cleanup triggers with tier awareness."""
        # Test tier-aware buffer allocation
        for tier in [PoolTier.SMALL, PoolTier.MEDIUM, PoolTier.LARGE]:
            buffer = await self.coordinator.allocate_buffer(tier)
            stats = await self.coordinator.get_resource_stats()
            
            # Verify buffer size matches tier
            self.assertEqual(len(buffer), self.processor.config['tier_sizes'][tier])
            
            # Verify proper resource tracking
            self.assertEqual(stats['buffers_by_tier'][tier], 1)
            
            # Release buffer
            await self.coordinator.release_buffer(buffer)
        
        # Test cleanup triggers
        await self.processor.set_memory_threshold(1024)
        should_cleanup = await self.processor.should_cleanup()
        self.assertTrue(should_cleanup)
        
        # Verify metrics
        memory_stats = await self.processor.get_memory_stats()
        self.log_metric("memory_usage", memory_stats['usage'])
        self.log_metric("memory_threshold", await self.processor.get_memory_threshold())
        self.log_metric("tier_transitions", memory_stats['tier_transitions'])
        
    @pytest.mark.fast
    async def test_audio_processing(self):
        """Test core audio signal processing functionality with resource management."""
        # Create test audio data - 1 second of 440Hz sine wave
        sample_rate = 48000
        duration = 1.0  # seconds
        t = np.arange(int(sample_rate * duration)) / sample_rate
        frequency = 440  # Hz
        test_data = np.sin(2 * np.pi * frequency * t)
        test_bytes = (test_data * 32767).astype(np.int16).tobytes()
        
        try:
            # Allocate processing buffer through coordinator
            buffer = await self.coordinator.allocate_buffer(PoolTier.MEDIUM)
            
            # Process audio with error handling and resource management
            processed, stats = await self.processor.process_audio(test_bytes, buffer, width=2)
            
            # Verify processing results
            self.assertIsNotNone(processed)
            self.assertIsNotNone(stats)
            self.assertTrue(0 <= stats.peak <= 1.0)
            
            # Verify signal quality and performance
            self.assertGreater(stats.quality, 0.5, "Signal quality too low")
            self.assertLess(stats.duration, 0.1, "Processing too slow")
            
            # Release buffer
            await self.coordinator.release_buffer(buffer)
            
        except Exception as e:
            self.logger.error(f"Audio processing failed: {e}", exc_info=True)
            raise
        
        # Log comprehensive metrics
        self.log_metric("input_size", len(test_bytes))
        self.log_metric("output_size", len(processed))
        self.log_metric("peak_level", stats.peak)
        self.log_metric("processing_time", stats.duration)
        self.log_metric("buffer_utilization", stats.buffer_utilization)
        
    @pytest.mark.fast
    async def test_fallback_processing(self):
        """Test emergency fallback processing mode with resource constraints."""
        # Create test data - 1 second of silence
        test_data = b'\x00\x80' * 1000  # Alternating zeros and mid-scale values
        
        try:
            # Allocate minimal buffer for fallback
            buffer = await self.coordinator.allocate_buffer(PoolTier.SMALL)
            
            # Test fallback processing with resource management
            result = await self.processor.emergency_fallback(test_data, buffer)
            
            # Verify fallback output
            self.assertIsInstance(result, bytes)
            self.assertEqual(len(result), len(test_data))
            
            # Release buffer
            await self.coordinator.release_buffer(buffer)
            
        except Exception as e:
            self.logger.error(f"Fallback processing failed: {e}", exc_info=True)
            raise
        
        # Log comprehensive metrics
        self.log_metric("fallback_input_size", len(test_data))
        self.log_metric("fallback_output_size", len(result))
        self.log_metric("fallback_buffer_size", len(buffer))
        
    @pytest.mark.fast
    async def test_signal_quality(self):
        """Test signal quality measurements and analysis with resource optimization."""
        # Create test signals with different qualities
        good_signal = np.sin(2 * np.pi * 1000 * np.arange(48000) / 48000)
        noisy_signal = good_signal + 0.1 * np.random.randn(48000)
        
        # Convert to audio format
        good_bytes = (good_signal * 32767).astype(np.int16).tobytes()
        noisy_bytes = (noisy_signal * 32767).astype(np.int16).tobytes()
        
        try:
            # Allocate processing buffers through coordinator
            buffer1 = await self.coordinator.allocate_buffer(PoolTier.MEDIUM)
            buffer2 = await self.coordinator.allocate_buffer(PoolTier.MEDIUM)
            
            # Process both signals with error handling and resource management
            good_result, good_stats = await self.processor.process_audio(good_bytes, buffer1, width=2)
            noisy_result, noisy_stats = await self.processor.process_audio(noisy_bytes, buffer2, width=2)
            
            # Verify quality metrics
            self.assertGreater(good_stats.quality, noisy_stats.quality)
            
            # Verify signal characteristics
            self.assertGreater(good_stats.quality, 0.8, "Clean signal quality too low")
            self.assertLess(noisy_stats.quality, 0.8, "Noisy signal quality too high")
            
            # Verify processing performance
            self.assertLess(good_stats.duration, 0.1, "Clean signal processing too slow")
            self.assertLess(noisy_stats.duration, 0.1, "Noisy signal processing too slow")
            
            # Release buffers
            await self.coordinator.release_buffer(buffer1)
            await self.coordinator.release_buffer(buffer2)
            
        except Exception as e:
            self.logger.error(f"Signal quality test failed: {e}", exc_info=True)
            raise
        
        # Log comprehensive metrics
        self.log_metric("clean_signal_quality", good_stats.quality)
        self.log_metric("noisy_signal_quality", noisy_stats.quality)
        self.log_metric("quality_difference", good_stats.quality - noisy_stats.quality)
        self.log_metric("clean_buffer_utilization", good_stats.buffer_utilization)
        self.log_metric("noisy_buffer_utilization", noisy_stats.buffer_utilization)
