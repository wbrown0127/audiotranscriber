"""
COMPONENT_NOTES:
{
    "name": "TestResourcePool",
    "type": "Test Suite",
    "description": "Core test suite for verifying tiered resource pool implementation, including buffer allocation, deallocation, and metrics tracking",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TRP[TestResourcePool] --> RP[ResourcePool]
                TRP --> PT[PoolTier]
                TRP --> MV[MemoryView]
                RP --> PT
                RP --> MV
                RP --> BM[BufferManager]
        ```",
        "dependencies": {
            "ResourcePool": "Main component under test",
            "PoolTier": "Buffer size tier management",
            "MemoryView": "Memory view optimization",
            "BufferManager": "Buffer lifecycle management"
        }
    },
    "notes": [
        "Tests basic buffer allocation and release",
        "Verifies pool size limits and constraints",
        "Tests LIFO buffer reuse optimization",
        "Validates memory view optimization",
        "Tests staged cleanup functionality",
        "Ensures thread-safe concurrent operations"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_resource_pool.py",
            "python -m pytest tests/core/test_resource_pool.py -k test_concurrent_access"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "threading",
            "typing"
        ],
        "system": {
            "memory": "1GB minimum for buffer tests",
            "cpu": "Multi-core recommended for concurrency tests"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds",
        "resource_usage": [
            "High memory usage during buffer tests",
            "Multiple concurrent threads",
            "Proper cleanup of allocated buffers"
        ]
    },
    "history": {
        "created": "2025-02-18",
        "enhanced": "2025-02-18",
        "enhancements": [
            "LIFO buffer reuse",
            "Memory view optimization",
            "Staged cleanup",
            "Enhanced metrics"
        ]
    }
}
"""

import pytest
import threading
import time
from typing import Dict, List
from src.audio_transcriber.resource_pool import ResourcePool, PoolTier

class TestResourcePool:
    """Test suite for ResourcePool functionality."""
    
    @pytest.fixture
    def monitoring_coordinator(self):
        """Create a monitoring coordinator for testing."""
        from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
        coordinator = MonitoringCoordinator()
        coordinator.start_monitoring()
        
        # Initialize resource pool through coordinator
        coordinator.initialize_resource_pool({
            'memory': 1024 * 1024 * 100,  # 100MB
            'threads': 4,
            'handles': 100,
            'buffer': {
                4096: 1000,    # Small buffers
                65536: 500,    # Medium buffers
                1048576: 100   # Large buffers
            }
        })
        
        # Initialize channels
        for channel in ['left', 'right']:
            coordinator.initialize_channel(channel)
            
        yield coordinator
        
        # Cleanup
        try:
            # Cleanup channels in reverse order
            for channel in ['right', 'left']:
                coordinator.cleanup_channel(channel)
            coordinator.stop_monitoring()
            coordinator.cleanup()
        except Exception as e:
            print(f"Error during coordinator cleanup: {e}")

    @pytest.fixture
    def pool(self, monitoring_coordinator) -> ResourcePool:
        """Create a resource pool for testing with proper initialization."""
        pool = ResourcePool(coordinator=monitoring_coordinator)
        
        # Initialize channel-specific pools
        for channel in ['left', 'right']:
            pool.initialize_channel_pool(channel)
            
        yield pool
        
        # Cleanup
        try:
            # Cleanup channel pools in reverse order
            for channel in ['right', 'left']:
                pool.cleanup_channel_pool(channel)
            pool.cleanup()
        except Exception as e:
            print(f"Error during pool cleanup: {e}")
        
    def test_basic_allocation(self, pool: ResourcePool):
        """Test basic buffer allocation and release with channel support."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # Test system-wide allocations
                            small = pool.allocate(2048)  # Should use 4KB tier
                            medium = pool.allocate(32768)  # Should use 64KB tier
                            large = pool.allocate(524288)  # Should use 1MB tier
                            
                            assert small is not None
                            assert medium is not None
                            assert large is not None
                            
                            # Verify sizes
                            assert len(small) == PoolTier.SMALL.value
                            assert len(medium) == PoolTier.MEDIUM.value
                            assert len(large) == PoolTier.LARGE.value
                            
                            # Test channel-specific allocations
                            channel_buffers = {}
                            for channel in ['left', 'right']:
                                channel_buffers[channel] = {
                                    'small': pool.allocate_channel_buffer(channel, 2048),
                                    'medium': pool.allocate_channel_buffer(channel, 32768),
                                    'large': pool.allocate_channel_buffer(channel, 524288)
                                }
                                
                                # Verify channel allocations
                                for size, buf in channel_buffers[channel].items():
                                    assert buf is not None
                                    if size == 'small':
                                        assert len(buf) == PoolTier.SMALL.value
                                    elif size == 'medium':
                                        assert len(buf) == PoolTier.MEDIUM.value
                                    else:
                                        assert len(buf) == PoolTier.LARGE.value
                            
                            # Release system-wide buffers
                            assert pool.release(small)
                            assert pool.release(medium)
                            assert pool.release(large)
                            
                            # Release channel-specific buffers
                            for channel in ['left', 'right']:
                                for buf in channel_buffers[channel].values():
                                    assert pool.release_channel_buffer(channel, buf)
                            
                            # Verify system-wide metrics
                            metrics = pool.get_metrics()
                            assert metrics['SMALL']['allocation_count'] == 1
                            assert metrics['MEDIUM']['allocation_count'] == 1
                            assert metrics['LARGE']['allocation_count'] == 1
                            assert metrics['SMALL']['current_used'] == 0
                            assert metrics['MEDIUM']['current_used'] == 0
                            assert metrics['LARGE']['current_used'] == 0
                            
                            # Verify channel-specific metrics
                            for channel in ['left', 'right']:
                                channel_metrics = pool.get_channel_metrics(channel)
                                assert channel_metrics['SMALL']['allocation_count'] == 1
                                assert channel_metrics['MEDIUM']['allocation_count'] == 1
                                assert channel_metrics['LARGE']['allocation_count'] == 1
                                assert channel_metrics['SMALL']['current_used'] == 0
                                assert channel_metrics['MEDIUM']['current_used'] == 0
                                assert channel_metrics['LARGE']['current_used'] == 0
        
        except Exception as e:
            print(f"Error during basic allocation test: {e}")
            raise
        
    def test_pool_limits(self, pool: ResourcePool):
        """Test pool size limits with channel support."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # Test system-wide pool limits
                            buffers = []
                            for _ in range(pool.max_small_buffers + 1):
                                buf = pool.allocate(2048)
                                if buf is not None:
                                    buffers.append(buf)
                            
                            assert len(buffers) == pool.max_small_buffers
                            
                            # Release system-wide buffers
                            for buf in buffers:
                                assert pool.release(buf)
                            
                            # Test channel-specific pool limits
                            channel_buffers = {}
                            for channel in ['left', 'right']:
                                channel_buffers[channel] = []
                                for _ in range(pool.max_small_buffers + 1):
                                    buf = pool.allocate_channel_buffer(channel, 2048)
                                    if buf is not None:
                                        channel_buffers[channel].append(buf)
                                
                                # Verify channel limits
                                assert len(channel_buffers[channel]) == pool.max_small_buffers
                                
                                # Release channel buffers
                                for buf in channel_buffers[channel]:
                                    assert pool.release_channel_buffer(channel, buf)
                                    
                            # Verify metrics
                            metrics = pool.get_metrics()
                            assert metrics['SMALL']['allocation_count'] == pool.max_small_buffers
                            assert metrics['SMALL']['current_used'] == 0
                            
                            # Verify channel metrics
                            for channel in ['left', 'right']:
                                channel_metrics = pool.get_channel_metrics(channel)
                                assert channel_metrics['SMALL']['allocation_count'] == pool.max_small_buffers
                                assert channel_metrics['SMALL']['current_used'] == 0
                                
        except Exception as e:
            print(f"Error during pool limits test: {e}")
            raise
            
    def test_buffer_reuse(self, pool: ResourcePool):
        """Test LIFO buffer reuse functionality with channel support."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # Test system-wide buffer reuse
                            buf1 = pool.allocate(2048)
                            buf2 = pool.allocate(2048)
                            assert buf1 is not None
                            assert buf2 is not None
                            
                            # Release in reverse order
                            assert pool.release(buf2)
                            assert pool.release(buf1)
                            
                            # Allocate again - should get buf1 first (LIFO)
                            new_buf1 = pool.allocate(2048)
                            new_buf2 = pool.allocate(2048)
                            assert new_buf1 is buf1  # Should get buf1 first
                            assert new_buf2 is buf2  # Then buf2
                            
                            # Test channel-specific buffer reuse
                            channel_buffers = {}
                            for channel in ['left', 'right']:
                                # Allocate channel buffers
                                buf1 = pool.allocate_channel_buffer(channel, 2048)
                                buf2 = pool.allocate_channel_buffer(channel, 2048)
                                assert buf1 is not None
                                assert buf2 is not None
                                channel_buffers[channel] = [buf1, buf2]
                                
                                # Release in reverse order
                                assert pool.release_channel_buffer(channel, buf2)
                                assert pool.release_channel_buffer(channel, buf1)
                                
                                # Allocate again - should get buf1 first (LIFO)
                                new_buf1 = pool.allocate_channel_buffer(channel, 2048)
                                new_buf2 = pool.allocate_channel_buffer(channel, 2048)
                                assert new_buf1 is buf1  # Should get buf1 first
                                assert new_buf2 is buf2  # Then buf2
                            
                            # Verify system-wide reuse metrics
                            metrics = pool.get_metrics()
                            assert metrics['SMALL']['reuse_count'] == 2
                            
                            # Verify channel-specific reuse metrics
                            for channel in ['left', 'right']:
                                channel_metrics = pool.get_channel_metrics(channel)
                                assert channel_metrics['SMALL']['reuse_count'] == 2
                                
                            # Release all buffers
                            assert pool.release(new_buf1)
                            assert pool.release(new_buf2)
                            for channel in ['left', 'right']:
                                for buf in channel_buffers[channel]:
                                    assert pool.release_channel_buffer(channel, buf)
                                    
        except Exception as e:
            print(f"Error during buffer reuse test: {e}")
            raise
        
    def test_memory_view_optimization(self, pool: ResourcePool):
        """Test memory view optimization with channel support."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # Test system-wide memory views
                            view = pool.allocate(2048, use_view=True)
                            assert isinstance(view, memoryview)
                            
                            # Test channel-specific memory views
                            channel_views = {}
                            for channel in ['left', 'right']:
                                channel_views[channel] = pool.allocate_channel_buffer(
                                    channel, 
                                    2048, 
                                    use_view=True
                                )
                                assert isinstance(channel_views[channel], memoryview)
                            
                            # Verify system-wide view metrics
                            metrics = pool.get_metrics()
                            assert metrics['SMALL']['view_count'] == 1
                            
                            # Verify channel-specific view metrics
                            for channel in ['left', 'right']:
                                channel_metrics = pool.get_channel_metrics(channel)
                                assert channel_metrics['SMALL']['view_count'] == 1
                            
                            # Release system-wide view
                            assert pool.release(view)
                            
                            # Release channel-specific views
                            for channel in ['left', 'right']:
                                assert pool.release_channel_buffer(channel, channel_views[channel])
                            
                            # Verify proper cleanup
                            stats = pool.get_pool_stats()
                            assert stats['SMALL']['views'] == 0
                            
                            # Verify channel cleanup
                            for channel in ['left', 'right']:
                                channel_stats = pool.get_channel_pool_stats(channel)
                                assert channel_stats['SMALL']['views'] == 0
            
        except Exception as e:
            print(f"Error during memory view optimization test: {e}")
            raise
        
    def test_staged_cleanup(self, pool: ResourcePool):
        """Test staged cleanup functionality with channel support."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # Allocate system-wide buffers
                            buffers = []
                            for _ in range(5):
                                buf = pool.allocate(2048)
                                assert buf is not None
                                buffers.append(buf)
                            
                            # Allocate channel-specific buffers
                            channel_buffers = {}
                            for channel in ['left', 'right']:
                                channel_buffers[channel] = []
                                for _ in range(5):
                                    buf = pool.allocate_channel_buffer(channel, 2048)
                                    assert buf is not None
                                    channel_buffers[channel].append(buf)
                            
                            # Start staged cleanup
                            with pool.cleanup_stage():
                                # Release system-wide buffers in staged mode
                                for buf in buffers:
                                    assert pool.release(buf, staged=True)
                                
                                # Release channel-specific buffers in staged mode
                                for channel in ['left', 'right']:
                                    for buf in channel_buffers[channel]:
                                        assert pool.release_channel_buffer(channel, buf, staged=True)
                                
                                # Verify system-wide buffers are pending release
                                stats = pool.get_pool_stats()
                                assert stats['SMALL']['pending_releases'] == 5
                                
                                # Verify channel-specific buffers are pending release
                                for channel in ['left', 'right']:
                                    channel_stats = pool.get_channel_pool_stats(channel)
                                    assert channel_stats['SMALL']['pending_releases'] == 5
                                
                                # Verify metrics during cleanup
                                metrics = pool.get_metrics()
                                assert metrics['SMALL']['staged_count'] == 5
                                assert metrics['SMALL']['current_used'] == 5
                                
                                # Verify channel metrics during cleanup
                                for channel in ['left', 'right']:
                                    channel_metrics = pool.get_channel_metrics(channel)
                                    assert channel_metrics['SMALL']['staged_count'] == 5
                                    assert channel_metrics['SMALL']['current_used'] == 5
                            
                            # After cleanup stage, verify system-wide buffers are released
                            stats = pool.get_pool_stats()
                            assert stats['SMALL']['pending_releases'] == 0
                            assert stats['SMALL']['pool_size'] == 5
                            assert stats['SMALL']['allocated'] == 0
                            
                            # Verify channel-specific buffers are released
                            for channel in ['left', 'right']:
                                channel_stats = pool.get_channel_pool_stats(channel)
                                assert channel_stats['SMALL']['pending_releases'] == 0
                                assert channel_stats['SMALL']['pool_size'] == 5
                                assert channel_stats['SMALL']['allocated'] == 0
            
        except Exception as e:
            print(f"Error during staged cleanup test: {e}")
            raise
        
    def test_concurrent_access(self, pool: ResourcePool):
        """Test concurrent allocations and releases with channel support."""
        try:
            THREAD_COUNT = 10
            OPERATIONS_PER_THREAD = 100
            BUFFER_SIZES = [2048, 32768, 524288]  # Test all tiers
            
            # Track allocated buffers and metrics using thread-safe collections
            allocated = {
                'system': {i: {size: [] for size in BUFFER_SIZES} for i in range(THREAD_COUNT)},
                'left': {i: {size: [] for size in BUFFER_SIZES} for i in range(THREAD_COUNT)},
                'right': {i: {size: [] for size in BUFFER_SIZES} for i in range(THREAD_COUNT)}
            }
            locks = {
                'system': {i: threading.Lock() for i in range(THREAD_COUNT)},
                'left': {i: threading.Lock() for i in range(THREAD_COUNT)},
                'right': {i: threading.Lock() for i in range(THREAD_COUNT)}
            }
            
            # Track performance metrics
            success_counts = {
                'system': {size: 0 for size in BUFFER_SIZES},
                'left': {size: 0 for size in BUFFER_SIZES},
                'right': {size: 0 for size in BUFFER_SIZES}
            }
            success_locks = {
                'system': threading.Lock(),
                'left': threading.Lock(),
                'right': threading.Lock()
            }
            
            def worker(thread_id: int):
                """Worker function for concurrent testing."""
                try:
                    for _ in range(OPERATIONS_PER_THREAD):
                        if pool.shutdown_event.is_set():
                            return
                            
                        # Test all buffer sizes
                        for size in BUFFER_SIZES:
                            # System-wide allocation
                            buf = pool.allocate(size)
                            if buf is not None:
                                with locks['system'][thread_id]:
                                    allocated['system'][thread_id][size].append(buf)
                                time.sleep(0.001)  # Simulate work
                                assert pool.release(buf)
                                with locks['system'][thread_id]:
                                    allocated['system'][thread_id][size].remove(buf)
                                with success_locks['system']:
                                    success_counts['system'][size] += 1
                            
                            # Channel-specific allocations
                            for channel in ['left', 'right']:
                                buf = pool.allocate_channel_buffer(channel, size)
                                if buf is not None:
                                    with locks[channel][thread_id]:
                                        allocated[channel][thread_id][size].append(buf)
                                    time.sleep(0.001)  # Simulate work
                                    assert pool.release_channel_buffer(channel, buf)
                                    with locks[channel][thread_id]:
                                        allocated[channel][thread_id][size].remove(buf)
                                    with success_locks[channel]:
                                        success_counts[channel][size] += 1
                                    
                except Exception as e:
                    pool.record_thread_error(e)
                    
            # Start threads
            threads = []
            for i in range(THREAD_COUNT):
                t = threading.Thread(target=worker, args=(i,))
                t.start()
                threads.append(t)
                
            # Wait for completion
            for t in threads:
                t.join()
                
            # Verify all buffers were released and count successes
            metrics = pool.get_metrics()
            for tier, size in [('SMALL', 2048), ('MEDIUM', 32768), ('LARGE', 524288)]:
                assert metrics[tier]['current_used'] == 0
                # Verify successful operations
                assert success_counts['system'][size] > 0, f"No successful system allocations for {tier}"
                
            # Verify channel-specific metrics and successes
            for channel in ['left', 'right']:
                channel_metrics = pool.get_channel_metrics(channel)
                for tier, size in [('SMALL', 2048), ('MEDIUM', 32768), ('LARGE', 524288)]:
                    assert channel_metrics[tier]['current_used'] == 0
                    # Verify successful operations
                    assert success_counts[channel][size] > 0, f"No successful {channel} allocations for {tier}"
            
            # Verify no leftover buffers
            for thread_id in range(THREAD_COUNT):
                for pool_type in ['system', 'left', 'right']:
                    with locks[pool_type][thread_id]:
                        for size in BUFFER_SIZES:
                            assert len(allocated[pool_type][thread_id][size]) == 0
            
        except Exception as e:
            print(f"Error during concurrent access test: {e}")
            raise
        
    def test_metrics_tracking(self, pool: ResourcePool):
        """Test metrics tracking accuracy with channel support."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # System-wide operations
                            buffers = []
                            views = []
                            
                            # Channel-specific operations
                            channel_buffers = {channel: [] for channel in ['left', 'right']}
                            channel_views = {channel: [] for channel in ['left', 'right']}
                            
                            # Allocate system-wide buffers and views
                            for _ in range(3):
                                buf = pool.allocate(2048)
                                view = pool.allocate(2048, use_view=True)
                                assert buf is not None
                                assert view is not None
                                buffers.append(buf)
                                views.append(view)
                            
                            # Allocate channel-specific buffers and views
                            for channel in ['left', 'right']:
                                for _ in range(3):
                                    buf = pool.allocate_channel_buffer(channel, 2048)
                                    view = pool.allocate_channel_buffer(channel, 2048, use_view=True)
                                    assert buf is not None
                                    assert view is not None
                                    channel_buffers[channel].append(buf)
                                    channel_views[channel].append(view)
                            
                            # Release some normally, some staged
                            assert pool.release(buffers[0])
                            assert pool.release(views[0])
                            
                            for channel in ['left', 'right']:
                                assert pool.release_channel_buffer(channel, channel_buffers[channel][0])
                                assert pool.release_channel_buffer(channel, channel_views[channel][0])
                            
                            with pool.cleanup_stage():
                                # Stage system-wide releases
                                assert pool.release(buffers[1], staged=True)
                                assert pool.release(views[1], staged=True)
                                
                                # Stage channel-specific releases
                                for channel in ['left', 'right']:
                                    assert pool.release_channel_buffer(channel, channel_buffers[channel][1], staged=True)
                                    assert pool.release_channel_buffer(channel, channel_views[channel][1], staged=True)
                                
                                # Verify metrics during cleanup
                                metrics = pool.get_metrics()
                                assert metrics['SMALL']['staged_count'] == 2
                                assert metrics['SMALL']['current_used'] == 4
                                
                                # Verify channel metrics during cleanup
                                for channel in ['left', 'right']:
                                    channel_metrics = pool.get_channel_metrics(channel)
                                    assert channel_metrics['SMALL']['staged_count'] == 2
                                    assert channel_metrics['SMALL']['current_used'] == 4
                            
                            # Release remaining buffers
                            assert pool.release(buffers[2])
                            assert pool.release(views[2])
                            
                            for channel in ['left', 'right']:
                                assert pool.release_channel_buffer(channel, channel_buffers[channel][2])
                                assert pool.release_channel_buffer(channel, channel_views[channel][2])
                            
                            # Verify final system-wide metrics
                            metrics = pool.get_metrics()
                            assert metrics['SMALL']['total_allocated'] == 6
                            assert metrics['SMALL']['current_used'] == 0
                            assert metrics['SMALL']['view_count'] == 3
                            assert metrics['SMALL']['staged_count'] == 2
                            
                            # Verify final channel metrics
                            for channel in ['left', 'right']:
                                channel_metrics = pool.get_channel_metrics(channel)
                                assert channel_metrics['SMALL']['total_allocated'] == 6
                                assert channel_metrics['SMALL']['current_used'] == 0
                                assert channel_metrics['SMALL']['view_count'] == 3
                                assert channel_metrics['SMALL']['staged_count'] == 2
            
        except Exception as e:
            print(f"Error during metrics tracking test: {e}")
            raise
        
    def test_cleanup(self, pool: ResourcePool):
        """Test pool cleanup functionality with channel support."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # Allocate system-wide buffers
                            buffers = [
                                pool.allocate(2048),  # Regular buffer
                                pool.allocate(2048, use_view=True),  # Memory view
                                pool.allocate(32768),  # Medium buffer
                                pool.allocate(524288)  # Large buffer
                            ]
                            assert all(buf is not None for buf in buffers)
                            
                            # Allocate channel-specific buffers
                            channel_buffers = {}
                            for channel in ['left', 'right']:
                                channel_buffers[channel] = [
                                    pool.allocate_channel_buffer(channel, 2048),  # Regular buffer
                                    pool.allocate_channel_buffer(channel, 2048, use_view=True),  # Memory view
                                    pool.allocate_channel_buffer(channel, 32768),  # Medium buffer
                                    pool.allocate_channel_buffer(channel, 524288)  # Large buffer
                                ]
                                assert all(buf is not None for buf in channel_buffers[channel])
                            
                            # Clean up pools
                            pool.cleanup()
                            
                            # Verify system-wide cleanup
                            stats = pool.get_pool_stats()
                            for tier in ['SMALL', 'MEDIUM', 'LARGE']:
                                assert stats[tier]['pool_size'] == 0
                                assert stats[tier]['allocated'] == 0
                                assert stats[tier]['views'] == 0
                                assert stats[tier]['pending_releases'] == 0
                            
                            # Verify channel-specific cleanup
                            for channel in ['left', 'right']:
                                channel_stats = pool.get_channel_pool_stats(channel)
                                for tier in ['SMALL', 'MEDIUM', 'LARGE']:
                                    assert channel_stats[tier]['pool_size'] == 0
                                    assert channel_stats[tier]['allocated'] == 0
                                    assert channel_stats[tier]['views'] == 0
                                    assert channel_stats[tier]['pending_releases'] == 0
            
        except Exception as e:
            print(f"Error during cleanup test: {e}")
            raise
            
    def test_resource_ownership(self, pool: ResourcePool):
        """Test resource ownership verification and proper sharing."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # Test system-wide ownership
                            owner1_buffers = []
                            owner2_buffers = []
                            
                            # Allocate buffers with different owners
                            for _ in range(3):
                                buf1 = pool.allocate(2048, owner="owner1")
                                buf2 = pool.allocate(2048, owner="owner2")
                                assert buf1 is not None
                                assert buf2 is not None
                                owner1_buffers.append(buf1)
                                owner2_buffers.append(buf2)
                            
                            # Verify ownership metrics
                            metrics = pool.get_metrics()
                            assert metrics['SMALL']['owner_count'] == 2
                            assert metrics['SMALL']['owner_allocations']['owner1'] == 3
                            assert metrics['SMALL']['owner_allocations']['owner2'] == 3
                            
                            # Test channel-specific ownership
                            channel_buffers = {}
                            for channel in ['left', 'right']:
                                channel_buffers[channel] = {
                                    'owner1': [],
                                    'owner2': []
                                }
                                # Allocate channel buffers with different owners
                                for _ in range(3):
                                    buf1 = pool.allocate_channel_buffer(channel, 2048, owner="owner1")
                                    buf2 = pool.allocate_channel_buffer(channel, 2048, owner="owner2")
                                    assert buf1 is not None
                                    assert buf2 is not None
                                    channel_buffers[channel]['owner1'].append(buf1)
                                    channel_buffers[channel]['owner2'].append(buf2)
                                
                                # Verify channel ownership metrics
                                channel_metrics = pool.get_channel_metrics(channel)
                                assert channel_metrics['SMALL']['owner_count'] == 2
                                assert channel_metrics['SMALL']['owner_allocations']['owner1'] == 3
                                assert channel_metrics['SMALL']['owner_allocations']['owner2'] == 3
                            
                            # Test invalid owner release
                            with pytest.raises(ValueError):
                                pool.release(owner1_buffers[0], owner="wrong_owner")
                            
                            # Test channel-specific invalid owner release
                            for channel in ['left', 'right']:
                                with pytest.raises(ValueError):
                                    pool.release_channel_buffer(
                                        channel,
                                        channel_buffers[channel]['owner1'][0],
                                        owner="wrong_owner"
                                    )
                            
                            # Release system-wide buffers with correct owners
                            for buf in owner1_buffers:
                                assert pool.release(buf, owner="owner1")
                            for buf in owner2_buffers:
                                assert pool.release(buf, owner="owner2")
                            
                            # Release channel-specific buffers with correct owners
                            for channel in ['left', 'right']:
                                for buf in channel_buffers[channel]['owner1']:
                                    assert pool.release_channel_buffer(channel, buf, owner="owner1")
                                for buf in channel_buffers[channel]['owner2']:
                                    assert pool.release_channel_buffer(channel, buf, owner="owner2")
                            
                            # Verify cleanup
                            metrics = pool.get_metrics()
                            assert metrics['SMALL']['owner_count'] == 0
                            assert metrics['SMALL']['current_used'] == 0
                            
                            for channel in ['left', 'right']:
                                channel_metrics = pool.get_channel_metrics(channel)
                                assert channel_metrics['SMALL']['owner_count'] == 0
                                assert channel_metrics['SMALL']['current_used'] == 0
                                
        except Exception as e:
            print(f"Error during resource ownership test: {e}")
            raise

    def test_invalid_operations(self, pool: ResourcePool):
        """Test handling of invalid operations with channel support."""
        try:
            # Test with proper lock ordering
            with pool.state_lock:
                with pool.metrics_lock:
                    with pool.perf_lock:
                        with pool.component_lock:
                            # Test system-wide invalid operations
                            # Try to allocate buffer larger than largest tier
                            buf = pool.allocate(2 * 1024 * 1024)  # 2MB
                            assert buf is None
                            
                            # Try to release non-existent buffer
                            assert not pool.release(bytearray(1024))
                            
                            # Try to release same buffer twice
                            buf = pool.allocate(2048)
                            assert buf is not None
                            assert pool.release(buf)
                            assert not pool.release(buf)
                            
                            # Try to release invalid memory view
                            assert not pool.release(memoryview(bytearray(1024)))
                            
                            # Test channel-specific invalid operations
                            for channel in ['left', 'right']:
                                # Try to allocate buffer larger than largest tier
                                buf = pool.allocate_channel_buffer(channel, 2 * 1024 * 1024)  # 2MB
                                assert buf is None
                                
                                # Try to release non-existent buffer
                                assert not pool.release_channel_buffer(channel, bytearray(1024))
                                
                                # Try to release same buffer twice
                                buf = pool.allocate_channel_buffer(channel, 2048)
                                assert buf is not None
                                assert pool.release_channel_buffer(channel, buf)
                                assert not pool.release_channel_buffer(channel, buf)
                                
                                # Try to release invalid memory view
                                assert not pool.release_channel_buffer(channel, memoryview(bytearray(1024)))
                                
                                # Try to use invalid channel name
                                assert pool.allocate_channel_buffer('invalid_channel', 2048) is None
                                assert not pool.release_channel_buffer('invalid_channel', bytearray(1024))
            
        except Exception as e:
            print(f"Error during invalid operations test: {e}")
            raise
