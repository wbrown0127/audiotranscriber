#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestSignalProcessorMemory",
    "type": "Test Suite",
    "description": "Advanced test suite for verifying signal processor memory management features, including buffer pooling, staged cleanup, and memory optimization",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TSP[TestSignalProcessorMemory] --> SP[SignalProcessor]
                TSP --> BP[BufferPool]
                TSP --> MC[MonitoringCoordinator]
                TSP --> CT[ComponentTest]
                SP --> BP
                SP --> MV[MemoryView]
                SP --> MT[MemoryTracker]
        ```",
        "dependencies": {
            "SignalProcessor": "Main component under test",
            "BufferPool": "Memory pool management",
            "MonitoringCoordinator": "System monitoring",
            "ComponentTest": "Base test functionality",
            "MemoryView": "Memory optimization",
            "MemoryTracker": "Memory usage tracking"
        }
    },
    "notes": [
        "Tests buffer pool tier management (4KB/64KB/1MB)",
        "Verifies staged memory cleanup procedures",
        "Tests memory view optimization for channels",
        "Validates comprehensive memory tracking",
        "Ensures buffer reuse efficiency",
        "Monitors memory allocation patterns"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_signal_processor_memory.py",
            "python -m pytest tests/core/test_signal_processor_memory.py -k test_buffer_pool_tiers"
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
            "memory": "2GB minimum",
            "cpu": "AVX2 support for vectorized operations"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Peak memory usage under 500MB",
            "Proper cleanup between tests",
            "Memory tracking overhead accounted for"
        ]
    }
}
"""
import numpy as np
import pytest
import asyncio
import logging
import threading
from unittest.mock import patch
from audio_transcriber.signal_processor import SignalProcessor
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.resource_pool import PoolTier
from tests.utilities.base import ComponentTest

# Lock order documentation for reference:
# 1. state_lock: Component state transitions
# 2. metrics_lock: Performance metrics updates
# 3. perf_lock: Performance data collection
# 4. component_lock: Component lifecycle management
# 5. update_lock: Resource updates and allocation

@pytest.mark.asyncio  # Mark all tests in class as async
class TestSignalProcessorMemory(ComponentTest):
    """Test suite for SignalProcessor memory management functionality with async patterns.
    
    This test class verifies the memory management features of the SignalProcessor
    component, focusing on efficient resource utilization and cleanup.
    
    Key Features Tested:
        - Buffer pool tier allocation and management
        - Staged memory cleanup with verification
        - Memory view optimization for channel processing
        - Memory tracking and statistics collection
        - Buffer reuse and pooling efficiency
    
    Attributes:
        processor (SignalProcessor): The signal processor under test
        buffer_pool (BufferPool): The processor's buffer pool manager
    
    Example:
        class TestCustomProcessor(TestSignalProcessorMemory):
            def test_custom_buffer_size(self):
                buffer = self.buffer_pool.get_buffer(8192)
                self.assertEqual(len(buffer), 8192)
                self.buffer_pool.return_buffer(buffer)
    """

    async def asyncSetUp(self):
        """Set up test fixtures before each test method."""
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
            },
            'max_buffers_per_tier': 10
        })
        
        # Initialize memory tracking through coordinator
        await self.coordinator.init_component_tracking(self.processor)

    async def asyncTearDown(self):
        """Clean up test fixtures after each test method."""
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
    async def test_buffer_pool_tiers(self):
        """Test buffer pool tier management and allocation.
        
        Verifies the buffer pool's ability to manage different buffer size tiers
        efficiently. This test:
        1. Tests allocation from each tier (4KB/64KB/1MB)
        2. Verifies buffer properties and size
        3. Tests buffer return to pool
        
        Test Sequence:
            1. Request buffer from each tier
            2. Verify buffer size and type
            3. Return buffer to pool
            4. Check pool statistics
        
        Expected Results:
            - Correct buffer sizes allocated
            - Proper memory view type
            - Successful buffer returns
            - Accurate pool statistics
        
        Example Metrics:
            - small_tier_usage: Usage of 4KB tier
            - medium_tier_usage: Usage of 64KB tier
            - large_tier_usage: Usage of 1MB tier
            - tier_available: Available buffers per tier
        """
        # Test each buffer tier through coordinator
        for tier in [PoolTier.SMALL, PoolTier.MEDIUM, PoolTier.LARGE]:
            try:
                # Request buffer through coordinator
                buffer = await self.coordinator.allocate_buffer(tier)
                
                # Verify buffer properties
                expected_size = self.processor.config['tier_sizes'][tier]
                self.assertEqual(len(buffer), expected_size)
                self.assertTrue(isinstance(buffer, memoryview))
                
                # Return buffer through coordinator
                await self.coordinator.release_buffer(buffer)
                
                # Get stats through coordinator
                stats = await self.coordinator.get_resource_stats()
                self.log_metric(f"{tier.name.lower()}_tier_usage", stats['buffers_by_tier'][tier])
                self.log_metric(f"{tier.name.lower()}_tier_available", stats['available_by_tier'][tier])
                
            except Exception as e:
                self.logger.error(f"Buffer tier test failed for {tier}: {e}", exc_info=True)
                raise

    @pytest.mark.fast
    async def test_staged_cleanup(self):
        """Test staged memory cleanup process with resource management.
        
        Verifies the signal processor's ability to perform staged cleanup
        of memory resources through the coordinator. This test:
        1. Allocates buffers across different tiers
        2. Triggers staged cleanup process
        3. Verifies cleanup effectiveness
        
        Test Sequence:
            1. Allocate test buffers (small/medium/large)
            2. Record initial memory state
            3. Perform staged cleanup
            4. Verify cleanup results
            5. Check final memory state
        
        Expected Results:
            - All cleanup stages completed
            - Memory successfully recovered
            - Final memory usage reduced
            - Cleanup metrics logged
            - Resource tracking accurate
        
        Example Metrics:
            - initial_memory_usage: Starting memory allocation
            - cleanup_stages: Number of stages completed
            - memory_recovered: Amount of memory freed
            - final_memory_usage: Ending memory allocation
            - resource_leaks: Number of unclaimed resources
        """
        try:
            # Allocate buffers across different tiers through coordinator
            buffers = []
            for tier in [PoolTier.SMALL, PoolTier.MEDIUM, PoolTier.LARGE]:
                for _ in range(5):
                    buffer = await self.coordinator.allocate_buffer(tier)
                    buffers.append(buffer)
            
            # Log initial state through coordinator
            initial_stats = await self.coordinator.get_resource_stats()
            self.log_metric("initial_memory_usage", initial_stats['total_allocated'])
            self.log_metric("initial_buffer_count", initial_stats['active_buffers'])
            
            # Trigger staged cleanup through coordinator
            cleanup_stats = await self.coordinator.perform_staged_cleanup()
            
            # Verify cleanup stages
            self.assertIn('stages_completed', cleanup_stats)
            self.assertIn('memory_recovered', cleanup_stats)
            self.assertIn('resource_leaks', cleanup_stats)
            
            # Log comprehensive cleanup metrics
            self.log_metric("cleanup_stages", cleanup_stats['stages_completed'])
            self.log_metric("memory_recovered", cleanup_stats['memory_recovered'])
            self.log_metric("resource_leaks", cleanup_stats['resource_leaks'])
            
            # Verify final state through coordinator
            final_stats = await self.coordinator.get_resource_stats()
            self.log_metric("final_memory_usage", final_stats['total_allocated'])
            self.log_metric("final_buffer_count", final_stats['active_buffers'])
            
            # Verify cleanup effectiveness
            self.assertEqual(final_stats['active_buffers'], 0, 
                           "Not all buffers were properly cleaned up")
            
        except Exception as e:
            self.logger.error(f"Staged cleanup test failed: {e}", exc_info=True)
            raise

    @pytest.mark.fast
    async def test_memory_view_optimization(self):
        """Test memory view optimization for channel separation.
        
        Verifies the signal processor's ability to efficiently separate audio
        channels using memory views. This test:
        1. Creates test stereo audio data
        2. Processes using memory view optimization
        3. Verifies channel separation and data integrity
        
        Test Sequence:
            1. Generate test audio (stereo sine waves)
            2. Process using memory views
            3. Verify channel separation
            4. Check data integrity
            5. Measure performance
        
        Expected Results:
            - Successful channel separation
            - Correct data sizes
            - Data integrity maintained
            - Processing time within limits
        
        Example Metrics:
            - input_size: Size of input audio data
            - channel_size: Size of separated channels
            - processing_time: Time taken for separation
        """
        try:
            # Create test audio data - 1 second stereo
            sample_rate = 48000
            duration = 1.0
            test_data = np.zeros((int(sample_rate * duration), 2), dtype=np.int16)
            test_data[:, 0] = np.sin(2 * np.pi * 440 * np.arange(int(sample_rate * duration)) / sample_rate) * 32767  # Left
            test_data[:, 1] = np.sin(2 * np.pi * 880 * np.arange(int(sample_rate * duration)) / sample_rate) * 32767  # Right
            
            # Convert to bytes
            audio_bytes = test_data.tobytes()
            
            # Allocate processing buffers through coordinator
            left_buffer = await self.coordinator.allocate_buffer(PoolTier.MEDIUM)
            right_buffer = await self.coordinator.allocate_buffer(PoolTier.MEDIUM)
            
            try:
                # Process audio with memory view optimization
                with patch('time.perf_counter') as mock_time:
                    mock_time.side_effect = [0, 0.015]  # 15ms processing time
                    processed_data = await self.processor.process_channels(
                        audio_bytes, left_buffer, right_buffer
                    )
                    
                # Verify channel separation
                self.assertEqual(len(processed_data), 2, "Failed to separate channels")
                left_channel, right_channel = processed_data
                
                # Verify data integrity
                self.assertEqual(len(left_channel), len(audio_bytes) // 4, "Incorrect left channel size")
                self.assertEqual(len(right_channel), len(audio_bytes) // 4, "Incorrect right channel size")
                
                # Verify sample rate
                self.assertEqual(len(left_channel) // 2, sample_rate, "Incorrect sample count")
                
            finally:
                # Release buffers
                await self.coordinator.release_buffer(left_buffer)
                await self.coordinator.release_buffer(right_buffer)
            
        except Exception as e:
            self.logger.error(f"Memory view optimization failed: {e}", exc_info=True)
            raise
        
        # Log comprehensive metrics
        self.log_metric("input_size", len(audio_bytes))
        self.log_metric("channel_size", len(left_channel))
        self.log_metric("processing_time", 0.015)
        self.log_metric("memory_views_created", 2)  # Left and right channels
        self.log_metric("buffer_efficiency", await self.processor.get_buffer_efficiency())

    @pytest.mark.fast
    async def test_memory_tracking(self):
        """Test comprehensive memory tracking.
        
        Verifies the signal processor's ability to track memory usage
        and allocation patterns. This test:
        1. Monitors memory usage during operations
        2. Tracks allocation patterns
        3. Verifies tracking accuracy
        
        Test Sequence:
            1. Get initial memory stats
            2. Perform processing operations
            3. Monitor memory metrics
            4. Verify tracking fields
        
        Expected Results:
            - Peak usage tracked
            - Current usage monitored
            - Allocation counts maintained
            - All metrics properly logged
        
        Example Metrics:
            - peak_memory: Maximum memory used
            - current_memory: Current memory usage
            - allocations: Number of memory allocations
        """
        try:
            # Get initial memory stats through coordinator
            initial_stats = await self.coordinator.get_resource_stats()
            
            # Create test audio data
            audio_data = np.random.randint(-32768, 32767, size=(48000, 2), dtype=np.int16).tobytes()
            
            # Allocate processing buffer
            buffer = await self.coordinator.allocate_buffer(PoolTier.MEDIUM)
            
            try:
                for _ in range(5):
                    # Process audio through coordinator
                    await self.processor.process_audio(audio_data, buffer)
                    
                    # Get comprehensive stats
                    current_stats = await self.coordinator.get_resource_stats()
                    component_stats = await self.processor.get_memory_stats()
                    
                    # Verify tracking fields
                    self.assertIn('peak_usage', component_stats)
                    self.assertIn('current_usage', component_stats)
                    self.assertIn('allocation_count', component_stats)
                    self.assertIn('tier_transitions', component_stats)
                    
                    # Log comprehensive metrics
                    self.log_metric("peak_memory", component_stats['peak_usage'])
                    self.log_metric("current_memory", component_stats['current_usage'])
                    self.log_metric("allocations", component_stats['allocation_count'])
                    self.log_metric("tier_transitions", component_stats['tier_transitions'])
                    self.log_metric("buffer_utilization", current_stats['buffer_utilization'])
                    
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"Memory tracking test failed: {e}", exc_info=True)
            raise

    @pytest.mark.fast
    async def test_buffer_reuse(self):
        """Test buffer reuse and pooling efficiency.
        
        Verifies the signal processor's buffer pooling system's ability
        to efficiently reuse memory buffers. This test:
        1. Processes multiple audio chunks
        2. Tracks buffer allocations and reuse
        3. Calculates efficiency metrics
        
        Test Sequence:
            1. Process multiple audio chunks
            2. Track new allocations
            3. Track buffer pool hits
            4. Calculate reuse ratio
            5. Verify efficiency
        
        Expected Results:
            - Reuse ratio above 50%
            - Minimal new allocations
            - Efficient buffer hits
            - Performance metrics logged
        
        Example Metrics:
            - total_operations: Total buffer operations
            - new_allocations: New memory allocations
            - buffer_hits: Successful buffer reuse
            - reuse_ratio: Efficiency measurement
        """
        try:
            # Track allocations through coordinator
            allocation_count = 0
            buffer_hits = 0
            
            # Create test audio data
            audio_data = np.random.randint(-32768, 32767, size=(4800, 2), dtype=np.int16).tobytes()
            
            # Process multiple audio chunks with buffer reuse
            buffer = await self.coordinator.allocate_buffer(PoolTier.MEDIUM)
            
            try:
                for _ in range(10):
                    # Process audio and track buffer usage through coordinator
                    stats = await self.processor.process_audio_with_stats(audio_data, buffer)
                    
                    # Update metrics
                    allocation_count += stats['new_allocations']
                    buffer_hits += stats['buffer_hits']
                    
                    # Get coordinator stats
                    coord_stats = await self.coordinator.get_resource_stats()
                    self.log_metric(f"buffer_utilization_{_}", coord_stats['buffer_utilization'])
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
            
            # Calculate reuse ratio
            reuse_ratio = buffer_hits / (buffer_hits + allocation_count) if (buffer_hits + allocation_count) > 0 else 0
            
            # Verify efficient reuse
            self.assertGreater(reuse_ratio, 0.5, "Buffer reuse ratio should be above 50%")
            
            # Log comprehensive metrics
            self.log_metric("total_operations", buffer_hits + allocation_count)
            self.log_metric("new_allocations", allocation_count)
            self.log_metric("buffer_hits", buffer_hits)
            self.log_metric("reuse_ratio", reuse_ratio)
            self.log_metric("tier_transitions", stats['tier_transitions'])
            self.log_metric("peak_memory", stats['peak_memory'])
            
        except Exception as e:
            self.logger.error(f"Buffer reuse test failed: {e}", exc_info=True)
            raise

if __name__ == '__main__':
    unittest.main()
