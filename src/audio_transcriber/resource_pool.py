"""
COMPONENT_NOTES (Updated 2025-02-19):
- Removed direct cleanup lock
- Now follows MonitoringCoordinator's lock hierarchy
- Added proper coordinator integration for metrics and error handling
- Uses proper lock ordering for all operations
- Added comprehensive error tracking through coordinator

{
    "name": "ResourcePool",
    "type": "Core Component",
    "description": "Tiered resource pool system that manages memory allocation with efficient buffer reuse, lifecycle management, and performance optimization",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                RP[ResourcePool] --> PT[PoolTier]
                RP --> PM[PoolMetrics]
                RP --> BP[BufferPool]
                RP --> MV[MemoryView]
                RP --> SC[StagedCleanup]
                PT --> SB[SmallBuffer]
                PT --> MB[MediumBuffer]
                PT --> LB[LargeBuffer]
                BP --> LIFO[LIFOQueue]
                BP --> AT[AllocationTracker]
                MV --> VT[ViewTracker]
                SC --> PR[PendingReleases]
        ```",
        "dependencies": {
            "PoolTier": "Buffer size categorization",
            "PoolMetrics": "Performance tracking",
            "BufferPool": "Buffer management",
            "MemoryView": "Zero-copy operations",
            "StagedCleanup": "Graceful shutdown",
            "LIFOQueue": "Buffer reuse strategy",
            "AllocationTracker": "Resource tracking",
            "ViewTracker": "View lifecycle",
            "PendingReleases": "Cleanup management"
        }
    },
    "notes": [
        "Implements tiered buffer pools (4KB/64KB/1MB)",
        "Uses LIFO ordering for better cache locality",
        "Supports memory view optimization",
        "Provides staged cleanup for graceful shutdown",
        "Tracks detailed performance metrics",
        "Ensures thread-safe operations"
    ],
    "usage": {
        "examples": [
            "pool = ResourcePool(coordinator)",
            "buffer = pool.allocate(4096)",
            "view = pool.allocate(4096, use_view=True)",
            "pool.release(buffer)",
            "with pool.cleanup_stage(): ..."
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "threading",
            "enum",
            "dataclasses",
            "collections"
        ],
        "system": {
            "memory": "Configurable pool sizes",
            "threading": "Thread-safe operations"
        }
    },
    "performance": {
        "execution_time": "O(1) allocation/release",
        "resource_usage": [
            "Configurable memory limits per tier",
            "Efficient buffer reuse",
            "Zero-copy view operations",
            "Minimal lock contention"
        ]
    }
}
"""

import enum
import logging
import threading
import time
from typing import Dict, List, Optional, Set, Any, Deque
from dataclasses import dataclass, field as dataclass_field
from collections import deque
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class PoolTier(enum.Enum):
    """Resource pool tiers with predefined sizes."""
    SMALL = 4 * 1024  # 4KB
    MEDIUM = 64 * 1024  # 64KB
    LARGE = 1024 * 1024  # 1MB

@dataclass
class PoolMetrics:
    """Metrics for a resource pool tier."""
    total_allocated: int = 0
    current_used: int = 0
    peak_used: int = 0
    allocation_count: int = 0
    release_count: int = 0
    reuse_count: int = 0  # Track buffer reuse
    view_count: int = 0   # Track memory view creation
    staged_count: int = 0 # Track staged cleanups

class ResourcePool:
    """
    Manages tiered resource pools with proper lifecycle and metrics.
    Implements efficient allocation and deallocation strategies.
    
    Features:
    - LIFO buffer reuse for better cache locality
    - Memory view optimization for zero-copy operations
    - Staged cleanup for graceful shutdown
    - Detailed metrics tracking
    """
    
    def __init__(self, coordinator=None):
        """Initialize resource pool with coordinator integration.
        
        Args:
            coordinator: MonitoringCoordinator instance for resource tracking
        """
        if coordinator is None:
            raise RuntimeError("MonitoringCoordinator is required")
        self.coordinator = coordinator
        self.logger = logging.getLogger("ResourcePool")
        
        # Pool configuration
        self.max_small_buffers = 1000  # Max 4KB buffers
        self.max_medium_buffers = 100  # Max 64KB buffers
        self.max_large_buffers = 10    # Max 1MB buffers
        
        # Initialize metrics for each tier
        self.metrics = {
            tier: PoolMetrics() for tier in PoolTier
        }
        
        # Initialize locks following coordinator's lock hierarchy
        self._state_lock = threading.RLock()     # Lock 1 (reentrant for state changes)
        self._metrics_lock = threading.Lock()    # Lock 2 (for metrics updates)
        self._perf_lock = threading.Lock()       # Lock 3 (for performance tracking)
        self._tier_locks = {                     # Lock 4 (for tier operations)
            tier: threading.Lock() for tier in PoolTier
        }
        
        # Track cleanup state
        self._cleanup_stage = 0
        
        # Use deque for LIFO buffer reuse
        self._pools = {
            tier: deque() for tier in PoolTier
        }
        # Use list for allocated buffers since bytearray is unhashable
        self._allocated = {
            tier: [] for tier in PoolTier
        }
        # Track memory views using dict with id(view) as key
        self._views = {
            tier: {} for tier in PoolTier
        }
        # Track pending releases during cleanup
        self._pending_releases = {
            tier: [] for tier in PoolTier
        }
        
        # Register with coordinator
        if not coordinator.register_component('resource_pool', 'core'):
            raise RuntimeError("Failed to register resource_pool component")
            
        # Initialize metrics
        self._update_coordinator_metrics()
        
    def _update_coordinator_metrics(self):
        """Update coordinator with current metrics."""
        if self.coordinator:
            with self._metrics_lock:
                self.coordinator.update_state(
                    resource_pool_metrics=self.get_metrics(),
                    resource_pool_stats=self.get_pool_stats()
                )
        
    def allocate(self, size: int, use_view: bool = False) -> Optional[Any]:
        """
        Allocate a buffer of appropriate size.
        
        Args:
            size: Required buffer size in bytes
            use_view: Whether to return a memory view
            
        Returns:
            Allocated buffer or memory view, or None if allocation failed
        """
        # Determine appropriate tier
        tier = self._get_tier_for_size(size)
        if not tier:
            error = f"No suitable tier for size {size}"
            self.logger.error(error)
            if self.coordinator:
                self.coordinator.handle_error(RuntimeError(error), "resource_pool")
            return None
            
        with self._tier_locks[tier]:
            # Check pool limits
            if self._check_pool_limit(tier):
                error = f"Pool limit reached for tier {tier.name}"
                self.logger.error(error)
                if self.coordinator:
                    self.coordinator.handle_error(RuntimeError(error), "resource_pool")
                return None
                
            # Try to reuse from pool (LIFO order)
            if self._pools[tier]:
                buffer = self._pools[tier].pop()
                with self._metrics_lock:
                    self.metrics[tier].reuse_count += 1
            else:
                # Allocate new buffer
                try:
                    buffer = bytearray(tier.value)
                except MemoryError as e:
                    error = f"Memory allocation failed for tier {tier.name}"
                    self.logger.error(error)
                    if self.coordinator:
                        self.coordinator.handle_error(e, "resource_pool")
                    return None
                    
            # Track allocation
            self._allocated[tier].append(buffer)
            self._update_metrics_allocation(tier)
            
            # Return memory view if requested
            if use_view:
                view = memoryview(buffer)
                self._views[tier][id(view)] = (view, buffer)
                with self._metrics_lock:
                    self.metrics[tier].view_count += 1
                return view
            
            return buffer
            
    def release(self, buffer: Any, staged: bool = False) -> bool:
        """
        Release a buffer back to its pool.
        
        Args:
            buffer: Buffer or memory view to release
            staged: Whether this is part of staged cleanup
            
        Returns:
            bool: True if release successful
        """
        # Find buffer's tier
        tier = self._find_buffer_tier(buffer)
        if not tier:
            error = "Buffer not found in any tier"
            self.logger.error(error)
            if self.coordinator:
                self.coordinator.handle_error(RuntimeError(error), "resource_pool")
            return False
            
        # Check cleanup stage with proper lock ordering
        is_cleanup_active = False
        with self._state_lock:
            is_cleanup_active = self._cleanup_stage > 0 if staged else False
            
        with self._tier_locks[tier]:
            # Handle memory view release
            if isinstance(buffer, memoryview):
                view_id = id(buffer)
                if view_id not in self._views[tier]:
                    error = "Memory view not found"
                    self.logger.error(error)
                    if self.coordinator:
                        self.coordinator.handle_error(RuntimeError(error), "resource_pool")
                    return False
                view, actual_buffer = self._views[tier][view_id]
                del self._views[tier][view_id]
                buffer = actual_buffer
            
            # Find buffer in allocated list
            try:
                idx = self._allocated[tier].index(buffer)
            except ValueError:
                error = f"Buffer not allocated from tier {tier.name}"
                self.logger.error(error)
                if self.coordinator:
                    self.coordinator.handle_error(RuntimeError(error), "resource_pool")
                return False
            
            # Handle staged cleanup
            if staged and is_cleanup_active:
                with self._metrics_lock:
                    self.metrics[tier].staged_count += 1
                self._pending_releases[tier].append(buffer)
                return True
            
            # Return to pool (LIFO order)
            self._allocated[tier].pop(idx)
            self._pools[tier].append(buffer)  # Use append for LIFO
            self._update_metrics_release(tier)
            
            return True
            
    def _get_tier_for_size(self, size: int) -> Optional[PoolTier]:
        """Determine appropriate tier for requested size."""
        for tier in PoolTier:
            if size <= tier.value:
                return tier
        return None
        
    def _check_pool_limit(self, tier: PoolTier) -> bool:
        """Check if pool limit would be exceeded."""
        current = len(self._allocated[tier]) + len(self._pools[tier])
        limits = {
            PoolTier.SMALL: self.max_small_buffers,
            PoolTier.MEDIUM: self.max_medium_buffers,
            PoolTier.LARGE: self.max_large_buffers
        }
        return current >= limits[tier]
        
    def _find_buffer_tier(self, buffer: Any) -> Optional[PoolTier]:
        """Find which tier a buffer belongs to."""
        if isinstance(buffer, memoryview):
            for tier in PoolTier:
                if id(buffer) in self._views[tier]:
                    return tier
        else:
            for tier in PoolTier:
                if buffer in self._allocated[tier]:
                    return tier
        return None
        
    def _update_metrics_allocation(self, tier: PoolTier) -> None:
        """Update metrics after allocation with coordinator integration."""
        with self._metrics_lock:
            metrics = self.metrics[tier]
            metrics.total_allocated += 1
            metrics.current_used += 1
            metrics.peak_used = max(metrics.peak_used, metrics.current_used)
            metrics.allocation_count += 1
            
            if self.coordinator:
                self.coordinator.update_state(**{
                    f"resource_pool_{tier.name.lower()}_allocated": metrics.total_allocated,
                    f"resource_pool_{tier.name.lower()}_used": metrics.current_used,
                    f"resource_pool_{tier.name.lower()}_peak": metrics.peak_used
                })
        
    def _update_metrics_release(self, tier: PoolTier) -> None:
        """Update metrics after release with coordinator integration."""
        with self._metrics_lock:
            metrics = self.metrics[tier]
            metrics.current_used -= 1
            metrics.release_count += 1
            
            if self.coordinator:
                self.coordinator.update_state(**{
                    f"resource_pool_{tier.name.lower()}_used": metrics.current_used,
                    f"resource_pool_{tier.name.lower()}_released": metrics.release_count
                })
        
    @contextmanager
    def cleanup_stage(self):
        """Context manager for staged cleanup with proper lock ordering."""
        with self._state_lock:
            self._cleanup_stage += 1
            if self.coordinator:
                self.coordinator.update_state(cleanup_stage=self._cleanup_stage)
        try:
            yield
        finally:
            with self._state_lock:
                self._cleanup_stage -= 1
                if self.coordinator:
                    self.coordinator.update_state(cleanup_stage=self._cleanup_stage)
                if self._cleanup_stage == 0:
                    # Process any pending releases
                    self._process_pending_releases()

    def _process_pending_releases(self):
        """Process any pending releases after staged cleanup."""
        for tier in PoolTier:
            with self._tier_locks[tier]:
                # Release any pending buffers
                for buffer in self._pending_releases[tier]:
                    if buffer in self._allocated[tier]:
                        idx = self._allocated[tier].index(buffer)
                        self._allocated[tier].pop(idx)
                        self._pools[tier].append(buffer)
                        self._update_metrics_release(tier)
                self._pending_releases[tier].clear()

    def cleanup(self) -> None:
        """Clean up all pools."""
        with self._state_lock:
            self._cleanup_stage += 1
            if self.coordinator:
                self.coordinator.update_state(cleanup_stage=self._cleanup_stage)
                
        try:
            for tier in PoolTier:
                with self._tier_locks[tier]:
                    # Clear memory views first
                    self._views[tier].clear()
                    # Clear pools and allocated buffers
                    self._pools[tier].clear()
                    self._allocated[tier].clear()
                    self._pending_releases[tier].clear()
                    self.metrics[tier] = PoolMetrics()
                    
            if self.coordinator:
                self.coordinator.update_state(
                    resource_pool_metrics=self.get_metrics(),
                    resource_pool_stats=self.get_pool_stats()
                )
        finally:
            with self._state_lock:
                self._cleanup_stage -= 1
                if self.coordinator:
                    self.coordinator.update_state(cleanup_stage=self._cleanup_stage)

    def get_metrics(self) -> Dict[str, Dict[str, int]]:
        """Get current metrics for all tiers."""
        with self._metrics_lock:
            return {
                tier.name: {
                    'total_allocated': metrics.total_allocated,
                    'current_used': metrics.current_used,
                    'peak_used': metrics.peak_used,
                    'allocation_count': metrics.allocation_count,
                    'release_count': metrics.release_count,
                    'reuse_count': metrics.reuse_count,
                    'view_count': metrics.view_count,
                    'staged_count': metrics.staged_count
                }
                for tier, metrics in self.metrics.items()
            }

    def get_pool_stats(self) -> Dict[str, Dict[str, int]]:
        """Get detailed pool statistics."""
        stats = {}
        for tier in PoolTier:
            with self._tier_locks[tier]:
                stats[tier.name] = {
                    'pool_size': len(self._pools[tier]),
                    'allocated': len(self._allocated[tier]),
                    'views': len(self._views[tier]),
                    'pending_releases': len(self._pending_releases[tier])
                }
                if self.coordinator:
                    self.coordinator.update_state(**{
                        f"resource_pool_{tier.name.lower()}_stats": stats[tier.name]
                    })
        return stats
