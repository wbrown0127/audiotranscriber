"""
COMPONENT_NOTES:
{
    "name": "SignalProcessor",
    "type": "Audio Processing Component",
    "description": "Thread-safe signal processor that handles audio processing, memory management, and channel synchronization through MonitoringCoordinator",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                SP[SignalProcessor] --> MC[MonitoringCoordinator]
                SP --> TR[Transcriber]
                SP --> AO[AudioOp]
                SP --> MM[MemoryManager]
                MC --> RP[ResourcePool]
                MC --> BM[BufferManager]
                MC --> CC[ComponentCoordinator]
        ```",
        "dependencies": {
            "MonitoringCoordinator": {
                "description": "Handles system monitoring and resource management",
                "responsibilities": [
                    "Resource allocation/deallocation",
                    "Buffer management",
                    "Component coordination",
                    "Error handling"
                ]
            },
            "Transcriber": {
                "description": "Handles audio transcription",
                "responsibilities": [
                    "Speech-to-text conversion",
                    "Audio analysis",
                    "Transcription optimization",
                    "Error recovery"
                ]
            },
            "AudioOp": {
                "description": "Provides audio processing operations",
                "responsibilities": [
                    "Channel separation",
                    "Signal analysis",
                    "Audio optimization",
                    "Quality metrics"
                ]
            },
            "MemoryManager": {
                "description": "Handles memory monitoring and cleanup",
                "responsibilities": [
                    "Memory tracking",
                    "Cleanup coordination",
                    "Resource optimization",
                    "Performance monitoring"
                ]
            }
        }
    },
    "notes": [
        "Implements adaptive buffer sizing based on processing load",
        "Provides fallback processing methods for error recovery",
        "Uses vectorized operations for efficient channel processing",
        "Maintains memory usage within configurable thresholds",
        "Uses MonitoringCoordinator for resource management",
        "Implements proper cleanup with channel awareness",
        "Provides comprehensive error handling and recovery"
    ],
    "usage": {
        "examples": [
            "processor = SignalProcessor(monitoring_coordinator)",
            "channels, stats = processor.process_audio(data)",
            "quality = processor.analyze_audio_quality(data, width)",
            "await processor.cleanup()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "numpy",
            "audioop",
            "psutil",
            "gc"
        ],
        "system": {
            "memory": "Managed through MonitoringCoordinator",
            "threading": "Thread-safe operations",
            "channels": "Stereo audio support"
        }
    },
    "performance": {
        "execution_time": {
            "channel_processing": "O(n) with vectorized operations",
            "quality_analysis": "O(n) with numpy optimizations",
            "cleanup": "Linear with buffer count"
        },
        "resource_usage": [
            "Efficient memory management",
            "Adaptive buffer sizing",
            "Channel-aware processing",
            "Optimized cleanup stages"
        ]
    }
}

"""

import audioop  # Using audioop-lts package for Python 3.13 compatibility
import numpy as np
import gc
import psutil
import time
from typing import Optional, Any, Dict
from typing_extensions import Tuple
from dataclasses import dataclass
from contextlib import contextmanager
@dataclass
class AudioStats:
    peak: float
    rms: float
    sample_width: int
    channels: int
    duration: float  # Processing duration in seconds
    quality: float  # Signal quality metric (0-1)

class SignalProcessor:
    def __init__(self, coordinator=None, transcriber=None, config: Optional[Dict] = None):
        """Initialize signal processor with optional configuration."""
        self.coordinator = coordinator
        self.transcriber = transcriber
        self._initialized = False
        
        # Default configuration
        self._config = {
            'sample_rate': 48000,
            'channels': 2,
            'width': 2,
            'memory_threshold': 1024 * 1024 * 100  # 100MB
        }
        
        # Memory management with fixed thresholds
        self.process = psutil.Process()
        self.memory_thresholds = {
            'soft_limit': 50 * 1024 * 1024,    # 50MB
            'hard_limit': 75 * 1024 * 1024,    # 75MB
            'emergency': 100 * 1024 * 1024     # 100MB
        }
        self.last_cleanup = {
            'gc': 0,
            'soft': 0,
            'hard': 0,
            'emergency': 0
        }
        # Dynamic cleanup intervals based on load
        self.cleanup_intervals = {
            'gc': lambda load: 30 if load < 0.5 else 15,      # 15-30s based on load
            'soft': lambda load: 60 if load < 0.5 else 30,    # 30-60s based on load
            'hard': lambda load: 300 if load < 0.5 else 60,   # 1-5min based on load
            'emergency': lambda _: 0                          # Always immediate
        }
        
        # Performance tracking
        self.stats_history = []
        self.last_allocation_count = 0
        
        # Processing configuration
        self.processing_queue_size = 0
        self.max_queue_size = 1024  # Maximum number of frames to queue
        self.processing_load = 0.0   # Current processing load (0-1)
        self.load_threshold = 0.8    # Threshold for high load detection
        
        # Channel synchronization
        self.channel_sync_window = 480  # 30ms at 16kHz
        self.max_sync_offset = 160  # Maximum allowed sync offset (10ms)
        self.sync_correlation_threshold = 0.7  # Minimum correlation for sync
        
        # Performance monitoring with enhanced memory tracking
        self.performance_stats = {
            'processing_time': [],  # List of recent processing times
            'queue_size': [],      # List of recent queue sizes
            'load_average': 0.0,   # Exponential moving average of load
            'sync_offsets': [],    # List of recent sync offsets
            'dropped_frames': 0,   # Count of dropped frames
            'recovery_count': 0,   # Count of recovery attempts
            'memory_usage': [],    # Memory usage history
            'buffer_tier_small': [],   # Small buffer usage (4KB)
            'buffer_tier_medium': [],  # Medium buffer usage (64KB)
            'buffer_tier_large': []    # Large buffer usage (1MB)
        }
        
        # Processing state
        self._is_recovering = False
        self._last_channel_state = None
        self._processing_start_time = None
        
        # Apply any provided configuration
        if config:
            self.configure(config)
            
        self._initialized = True

    def configure(self, config: Dict[str, Any]) -> None:
        """Configure signal processor parameters.
        
        Args:
            config: Configuration dictionary with parameters:
                - sample_rate: Audio sample rate in Hz
                - channels: Number of audio channels
                - width: Sample width in bytes
                - memory_threshold: Memory usage threshold in bytes
                - Optional: memory_thresholds for custom cleanup thresholds
        """
        self._config.update(config)
        
        # Update memory thresholds if provided
        if 'memory_thresholds' in config:
            self.memory_thresholds.update(config['memory_thresholds'])
            
        # Validate configuration
        if self._config['sample_rate'] <= 0:
            raise ValueError("Sample rate must be positive")
        if self._config['channels'] <= 0:
            raise ValueError("Channel count must be positive")
        if self._config['width'] not in (1, 2, 4):
            raise ValueError("Sample width must be 1, 2, or 4 bytes")
        if self._config['memory_threshold'] <= 0:
            raise ValueError("Memory threshold must be positive")
            
        # Reset performance tracking
        self.performance_stats['processing_time'].clear()
        self.performance_stats['queue_size'].clear()
        self.performance_stats['sync_offsets'].clear()
        self.performance_stats['dropped_frames'] = 0
        self.performance_stats['recovery_count'] = 0

    def emergency_fallback(self, data: bytes) -> Tuple[bytes, bytes]:
        """Emergency fallback for processing under high load.
        
        Provides basic channel separation without advanced processing.
        """
        try:
            # Basic channel separation using numpy
            arr = np.frombuffer(data, dtype=np.int16)
            left = arr[::2].tobytes()
            right = arr[1::2].tobytes()
            return left, right
        except Exception as e:
            self.coordinator.logger.error(f"Emergency fallback failed: {e}")
            # Return original data split in half as absolute fallback
            mid = len(data) // 2
            return data[:mid], data[mid:]

    def transcribe_audio(self, audio_data: bytes) -> None:
        """Transcribe audio data using configured transcriber.
        
        Args:
            audio_data: Audio data to transcribe
        """
        if not self.transcriber:
            return
            
        try:
            self.transcriber.process_audio(audio_data)
        except Exception as e:
            self.coordinator.logger.error(f"Transcription failed: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "signal_processor")

    def process_channels(self, data: bytes) -> Tuple[bytes, bytes]:
        """Process stereo audio data into separate channels using vectorized operations.
        
        Args:
            data: Raw stereo audio data
            
        Returns:
            Tuple of (left_channel, right_channel) audio data
            
        Note: Uses ResourcePool for efficient buffer management and proper cleanup
        """
        try:
            start_time = time.perf_counter()
            
            # Calculate buffer sizes
            view = memoryview(data).cast('h')  # Assuming 16-bit audio
            length = len(view) // 2
            buffer_size = length * 2
            
            # Allocate buffers through ResourcePool with error tracking
            left_buffer = right_buffer = None
            try:
                # Track allocation attempt
                self.last_allocation_count += 1
                allocation_id = f"alloc_{self.last_allocation_count}"
                
                self.coordinator.logger.debug(
                    f"Attempting buffer allocation {allocation_id} "
                    f"(size: {buffer_size})"
                )
                
                left_buffer = self.coordinator.allocate_resource(
                    'signal_processor_left', 
                    'buffer',
                    buffer_size
                )
                if not left_buffer:
                    self.coordinator.logger.error(
                        f"Left channel buffer allocation failed {allocation_id}"
                    )
                    return self.emergency_fallback(data)
                
                right_buffer = self.coordinator.allocate_resource(
                    'signal_processor_right', 
                    'buffer',
                    buffer_size
                )
                if not right_buffer:
                    self.coordinator.logger.error(
                        f"Right channel buffer allocation failed {allocation_id}"
                    )
                    if left_buffer:
                        self.coordinator.release_resource(
                            'signal_processor_left', 'buffer', left_buffer
                        )
                    return self.emergency_fallback(data)
                
                self.coordinator.logger.debug(
                    f"Successfully allocated buffers {allocation_id}"
                )
                
            except Exception as e:
                self.coordinator.logger.error(
                    f"Buffer allocation failed: {e}, attempting emergency fallback"
                )
                # Clean up any allocated buffers
                if left_buffer:
                    try:
                        self.coordinator.release_resource(
                            'signal_processor_left', 'buffer', left_buffer
                        )
                    except Exception as cleanup_error:
                        self.coordinator.logger.error(
                            f"Failed to clean up left buffer: {cleanup_error}"
                        )
                if right_buffer:
                    try:
                        self.coordinator.release_resource(
                            'signal_processor_right', 'buffer', right_buffer
                        )
                    except Exception as cleanup_error:
                        self.coordinator.logger.error(
                            f"Failed to clean up right buffer: {cleanup_error}"
                        )
                return self.emergency_fallback(data)
            
            try:
                # Use numpy's vectorized operations with memory tracking
                with self.memory_check():
                    buffer = np.frombuffer(data, dtype=np.int16).reshape(-1, 2)
                    left = np.frombuffer(left_buffer, dtype=np.int16)
                    right = np.frombuffer(right_buffer, dtype=np.int16)
                    
                    # Vectorized channel separation with memory monitoring
                    with np.nditer([buffer[:, 0], buffer[:, 1], left, right], 
                                 op_flags=[['readonly'], ['readonly'], 
                                         ['writeonly'], ['writeonly']]) as it:
                        for l_in, r_in, l_out, r_out in it:
                            l_out[...] = l_in
                            r_out[...] = r_in
                    
                    # Get the channel data as bytes
                    left_data = left.tobytes()
                    right_data = right.tobytes()
                    
                    # Update performance metrics
                    processing_time = time.perf_counter() - start_time
                    self._update_performance_metrics(
                        processing_time=processing_time,
                        buffer_size=buffer_size
                    )
                    
                    # Adjust window size based on performance
                    self._adjust_window_size(processing_time)
                    
                    return left_data, right_data
                    
            finally:
                # Release buffers back to pool with proper channel tracking
                self.coordinator.release_resource('signal_processor_left', 'buffer', left_buffer)
                self.coordinator.release_resource('signal_processor_right', 'buffer', right_buffer)
            
        except Exception as e:
            self.coordinator.logger.error(f"Channel separation failed: {e}")
            # Fallback to basic numpy operation
            return self.emergency_fallback(data)

    def process_audio(self, data: bytes, width: int = 2) -> Tuple[Tuple[bytes, bytes], Tuple[AudioStats, AudioStats]]:
        """Process stereo audio data with load management and channel sync."""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
        self._processing_start_time = time.perf_counter()
        self.processing_queue_size += 1
        
        try:
            with self.memory_check():
                # Check processing load
                if self._check_processing_load():
                    if not self._is_recovering:
                        self.coordinator.logger.warning("High processing load detected, entering recovery mode")
                        self._is_recovering = True
                        self.performance_stats['recovery_count'] += 1
                    return self.emergency_fallback(data), None
                else:
                    self._is_recovering = False
                    
                # Optimized channel separation
                left_channel, right_channel = self._optimize_channel_separation(data, width)
                
                # Synchronize channels if needed
                if self._needs_synchronization(left_channel, right_channel):
                    left_channel, right_channel = self._synchronize_channels(left_channel, right_channel)
                
                # Process each channel with optimized memory handling
                def process_channel(channel_data: np.ndarray) -> Tuple[bytes, AudioStats]:
                    try:
                        # Allocate buffer through coordinator
                        buffer = self.coordinator.allocate_resource('signal_processor', 'buffer', len(channel_data.tobytes()))
                        if not buffer:
                            return self.emergency_fallback(channel_data.tobytes())[0], None
                        
                        try:
                            # Copy data to buffer
                            np.copyto(np.frombuffer(buffer, dtype=channel_data.dtype), channel_data)
                            
                            # Convert to higher precision with load check
                            if self._check_processing_load():
                                return self.emergency_fallback(buffer)[0], None
                                
                            # Process in higher precision
                            converted = self.safe_call('lin2lin', buffer, width, 4)
                            
                            # Start timing
                            start_time = time.perf_counter()
                            
                            # Efficient statistics calculation using numpy
                            arr = np.frombuffer(converted, dtype=np.int32)
                            peak = float(np.max(np.abs(arr))) / (2**(8*4-1))
                            rms = float(np.sqrt(np.mean(arr.astype(np.float32)**2))) / (2**(8*4-1))

                            # Calculate quality metric (0-1) with vectorized operations
                            if rms < 1e-10:  # Very quiet or silent
                                quality = 0.0
                            else:
                                # Vectorized quality calculations
                                crest_factor = min(peak / rms, 20)
                                crest_score = np.exp(-0.5 * (crest_factor - 4)**2)
                                
                                level_score = min(1.0, peak * 2)
                                
                                clip_score = 1.0 - (peak / 0.99 if peak > 0.95 else 0)
                                
                                # Efficient zero crossing calculation
                                zero_crossings = np.sum(arr[1:] * arr[:-1] < 0)
                                noise_score = 1.0 - min(1.0, zero_crossings / (len(arr) * 0.5))
                                
                                # Weighted combination
                                quality = np.clip(
                                    0.3 * crest_score +
                                    0.3 * level_score +
                                    0.2 * clip_score +
                                    0.2 * noise_score,
                                    0.0, 1.0
                                )

                            # End timing
                            duration = time.perf_counter() - start_time
                            
                            stats = AudioStats(
                                peak=peak,
                                rms=rms,
                                sample_width=width,
                                channels=1,
                                duration=duration,
                                quality=quality
                            )
                            
                            return converted, stats
                            
                        finally:
                            # Release buffer back to pool
                            self.coordinator.release_resource('signal_processor', 'buffer', buffer)
                            
                    except Exception as e:
                        self.coordinator.logger.error(f"Channel processing failed: {e}")
                        return self.emergency_fallback(channel_data.tobytes())[0], None

                # Process both channels
                left_processed, left_stats = process_channel(left_channel)
                right_processed, right_stats = process_channel(right_channel)

                # Transcribe audio (for left channel for now, can be modified to handle both)
                self.transcribe_audio(left_processed)
                
                if self.coordinator:
                    with self.coordinator.processor_lock():
                        self.stats_history.extend([left_stats, right_stats])
                else:
                    self.stats_history.extend([left_stats, right_stats])
                    
                return (left_processed, right_processed), (left_stats, right_stats)
                
        except Exception as e:
            self.coordinator.logger.error(f"Audio processing failed: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "signal_processor")
            return self.emergency_fallback(data), None

    def get_performance_stats(self) -> dict:
        """Get performance statistics."""
        stats = {
            'memory_usage': self.process.memory_info().rss,
            'gc_collections': gc.get_count(),
            'stats_history_size': len(self.stats_history),
            'peak_values': [s.peak for s in self.stats_history[-10:] if s is not None],
            'processing_load': self.processing_load,
            'queue_size': self.processing_queue_size,
            'dropped_frames': self.performance_stats['dropped_frames'],
            'recovery_count': self.performance_stats['recovery_count']
        }
        
        if self.coordinator:
            self.coordinator.update_performance_stats('processor', stats)
            
        return stats

    def get_memory_stats(self) -> dict:
        """Get memory usage statistics."""
        memory_info = self.process.memory_info()
        return {
            'current_usage': memory_info.rss,
            'peak_usage': memory_info.peak_wset if hasattr(memory_info, 'peak_wset') else memory_info.rss,
            'available': psutil.virtual_memory().available,
            'thresholds': self.memory_thresholds,
            'gc_stats': {
                'collections': gc.get_count(),
                'objects': len(gc.get_objects()),
                'last_cleanup': self.last_cleanup
            }
        }

    def analyze_audio_quality(self, data: bytes, width: int) -> dict:
        """Analyze audio quality metrics."""
        try:
            with self.memory_check():
                # Calculate RMS level
                rms = self.safe_call('rms', data, width)
                
                # Calculate peak level
                peak = self.safe_call('max', data, width)
                
                # Calculate dynamic range
                dynamic_range = 20 * np.log10(peak / (rms + 1e-10))
                
                # Calculate noise floor (using lowest 10% of samples)
                arr = np.frombuffer(data, dtype=np.int16)
                noise_floor = np.percentile(np.abs(arr), 10)
                
                return {
                    'rms_level': float(rms) / (2**(8*width-1)),
                    'peak_level': float(peak) / (2**(8*width-1)),
                    'dynamic_range_db': dynamic_range,
                    'noise_floor': noise_floor / 32768.0
                }
                
        except Exception as e:
            self.coordinator.logger.error(f"Quality analysis failed: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "signal_processor")
            return {}

    def _adjust_window_size(self, processing_time: float) -> None:
        """Adjust processing window size based on performance metrics.
        
        Args:
            processing_time: Time taken to process current buffer
            
        Note: Dynamically adjusts window size to maintain optimal performance
        """
        # Calculate average processing time
        avg_processing_time = np.mean(self.performance_stats['processing_time'])
        
        # Adjust window size based on processing time thresholds
        if avg_processing_time > 0.005:  # 5ms threshold
            # Reduce window size if processing is slow
            new_window = max(240, self.channel_sync_window - 32)
            if new_window != self.channel_sync_window:
                self.coordinator.logger.debug(
                    f"Reducing window size: {self.channel_sync_window} -> {new_window} "
                    f"(avg processing time: {avg_processing_time*1000:.2f}ms)"
                )
                self.channel_sync_window = new_window
                
        elif avg_processing_time < 0.002:  # 2ms threshold
            # Increase window size if processing is fast
            new_window = min(960, self.channel_sync_window + 32)
            if new_window != self.channel_sync_window:
                self.coordinator.logger.debug(
                    f"Increasing window size: {self.channel_sync_window} -> {new_window} "
                    f"(avg processing time: {avg_processing_time*1000:.2f}ms)"
                )
                self.channel_sync_window = new_window
                
        # Update window size metrics
        if self.coordinator:
            self.coordinator.update_state(
                channel_sync_window=self.channel_sync_window,
                avg_processing_time=avg_processing_time * 1000  # Convert to ms
            )
            
    def _check_processing_load(self) -> bool:
        """Check if system is under high load."""
        # Update processing load using exponential moving average
        if self._processing_start_time is not None:
            current_load = (time.perf_counter() - self._processing_start_time) / 0.030  # 30ms target
            self.processing_load = 0.8 * self.processing_load + 0.2 * current_load
            
        # Update queue size tracking
        self.performance_stats['queue_size'].append(self.processing_queue_size)
        if len(self.performance_stats['queue_size']) > 100:
            self.performance_stats['queue_size'] = self.performance_stats['queue_size'][-100:]
            
        # Check if we're overloaded
        return (self.processing_load > self.load_threshold or 
                self.processing_queue_size > self.max_queue_size)

    def _optimize_channel_separation(self, data: bytes, width: int) -> Tuple[np.ndarray, np.ndarray]:
        """Optimized channel separation using memory views."""
        # Track memory usage before allocation
        initial_memory = self.process.memory_info().rss
        
        try:
            # Use memory view for efficient slicing
            view = memoryview(data).cast('h' if width == 2 else 'i')
            length = len(view) // 2
            
            # Pre-allocate arrays with memory tracking
            with self.memory_check():
                left = np.empty(length, dtype=np.int16 if width == 2 else np.int32)
                right = np.empty(length, dtype=np.int16 if width == 2 else np.int32)
            
            # Optimized channel separation with bounds checking
            if len(view) >= 2 * length:
                left[:] = view[::2]
                right[:] = view[1::2]
            else:
                raise ValueError(f"Invalid data length: {len(view)} for {length} samples")
            
            # Track memory usage after allocation
            final_memory = self.process.memory_info().rss
            memory_delta = final_memory - initial_memory
            
            if memory_delta > 1024 * 1024:  # More than 1MB
                self.coordinator.logger.warning(
                    f"Large memory allocation: {memory_delta/1024/1024:.1f}MB "
                    f"for channel separation"
                )
            
            return left, right
        except Exception as e:
            self.coordinator.logger.error(f"Channel separation failed: {e}")
            # Fallback to basic numpy operation
            arr = np.frombuffer(data, dtype=np.int16 if width == 2 else np.int32)
            return arr[::2], arr[1::2]

    def _synchronize_channels(self, left: np.ndarray, right: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Synchronize left and right channels using cross-correlation with proper resource management."""
        try:
            # Use a window of samples for correlation
            window_size = min(self.channel_sync_window, len(left), len(right))
            
            # Allocate window buffers through ResourcePool
            try:
                left_window_buffer = self.coordinator.allocate_resource('signal_processor', 'buffer', window_size * 2)
                if not left_window_buffer:
                    raise ValueError("Failed to allocate left window buffer")
                    
                try:
                    right_window_buffer = self.coordinator.allocate_resource('signal_processor', 'buffer', window_size * 2)
                    if not right_window_buffer:
                        raise ValueError("Failed to allocate right window buffer")
                        
                    # Copy window data
                    left_window = np.frombuffer(left_window_buffer, dtype=left.dtype)
                    right_window = np.frombuffer(right_window_buffer, dtype=right.dtype)
                    left_window[:] = left[:window_size]
                    right_window[:] = right[:window_size]
                    
                    # Calculate cross-correlation
                    correlation = np.correlate(left_window, right_window, mode='full')
                    max_corr_idx = np.argmax(correlation)
                    offset = max_corr_idx - (window_size - 1)
                    max_correlation = correlation[max_corr_idx]
                    
                finally:
                    # Release right window buffer
                    self.coordinator.release_resource('signal_processor', 'buffer', right_window_buffer)
                    
            finally:
                # Release left window buffer
                self.coordinator.release_resource('signal_processor', 'buffer', left_window_buffer)
            
            # Check if correlation is strong enough
            if max_correlation < self.sync_correlation_threshold * np.sqrt(np.sum(left_window**2) * np.sum(right_window**2)):
                return left, right  # Return original if correlation is weak
                
            # Apply offset if within limits
            if abs(offset) <= self.max_sync_offset:
                if offset > 0:
                    left = left[offset:]
                    right = right[:-offset] if offset > 0 else right
                else:
                    right = right[-offset:]
                    left = left[:offset] if offset < 0 else left
                    
                # Track sync offset
                self.performance_stats['sync_offsets'].append(offset)
                if len(self.performance_stats['sync_offsets']) > 100:
                    self.performance_stats['sync_offsets'] = self.performance_stats['sync_offsets'][-100:]
                    
            return left, right
            
        except Exception as e:
            self.coordinator.logger.error(f"Channel synchronization failed: {e}")
            return left, right  # Return original on error

    def _needs_synchronization(self, left: np.ndarray, right: np.ndarray) -> bool:
        """Check if channels need synchronization based on correlation."""
        try:
            # Use a small window for quick correlation check
            window_size = min(240, len(left), len(right))  # 15ms at 16kHz
            left_window = left[:window_size]
            right_window = right[:window_size]
            
            # Quick correlation check
            correlation = np.corrcoef(left_window, right_window)[0, 1]
            
            # If correlation is very high, no sync needed
            if correlation > 0.95:
                return False
                
            # If correlation is very low, might be different content
            if correlation < 0.2:
                return False
                
            # Check energy difference
            left_energy = np.sum(left_window**2)
            right_energy = np.sum(right_window**2)
            energy_ratio = min(left_energy, right_energy) / max(left_energy, right_energy)
            
            # Only sync if energy levels are comparable
            return energy_ratio > 0.5
            
        except Exception as e:
            self.coordinator.logger.error(f"Sync check failed: {e}")
            return False

    @contextmanager
    def memory_check(self):
        """Context manager for memory monitoring and cleanup."""
        try:
            yield
        finally:
            current_memory = self.process.memory_info().rss
            current_time = time.time()
            
            if self.coordinator:
                self.coordinator.update_state(memory_usage=current_memory)
            
            # Check thresholds from highest to lowest
            if current_memory > self.memory_thresholds['emergency']:
                self._emergency_cleanup()
            elif current_memory > self.memory_thresholds['hard_limit']:
                if current_time - self.last_cleanup['hard'] > self.cleanup_intervals['hard']:
                    self._hard_cleanup()
            elif current_memory > self.memory_thresholds['soft_limit']:
                if current_time - self.last_cleanup['soft'] > self.cleanup_intervals['soft']:
                    self._soft_cleanup()
            elif current_time - self.last_cleanup['gc'] > self.cleanup_intervals['gc']:
                self._gc_cleanup()

    def _emergency_cleanup(self):
        """Immediate aggressive cleanup."""
        if self.coordinator:
            with self.coordinator.processor_lock():
                # Force garbage collection
                gc.collect()
                # Clear history
                self.stats_history = self.stats_history[-10:]
                self.last_cleanup['emergency'] = time.time()
                self.coordinator.logger.warning("Emergency cleanup performed")

    def _hard_cleanup(self):
        """Strong cleanup for high memory usage."""
        if self.coordinator:
            with self.coordinator.processor_lock():
                # Run garbage collection
                gc.collect()
                # Trim history
                self.stats_history = self.stats_history[-50:]
                self.last_cleanup['hard'] = time.time()
                self.coordinator.logger.info("Hard cleanup performed")

    def _soft_cleanup(self):
        """Gentle cleanup for moderate memory usage."""
        if self.coordinator:
            with self.coordinator.processor_lock():
                # Run garbage collection
                gc.collect()
                # Trim history
                self.stats_history = self.stats_history[-100:]
                self.last_cleanup['soft'] = time.time()

    def _gc_cleanup(self):
        """Regular garbage collection."""
        gc.collect()
        self.last_cleanup['gc'] = time.time()
        
    def _update_performance_metrics(self, processing_time: float, buffer_size: int) -> None:
        """Update performance metrics with new processing data.
        
        Args:
            processing_time: Time taken to process current buffer
            buffer_size: Size of allocated buffer in bytes
        """
        # Update processing time history
        self.performance_stats['processing_time'].append(processing_time)
        if len(self.performance_stats['processing_time']) > 100:
            self.performance_stats['processing_time'] = self.performance_stats['processing_time'][-100:]
            
        # Update buffer usage metrics based on size
        if buffer_size <= 4 * 1024:  # 4KB
            self.performance_stats['buffer_tier_small'].append(buffer_size)
        elif buffer_size <= 64 * 1024:  # 64KB
            self.performance_stats['buffer_tier_medium'].append(buffer_size)
        else:  # 1MB
            self.performance_stats['buffer_tier_large'].append(buffer_size)
            
        # Trim buffer usage history
        for tier in ['small', 'medium', 'large']:
            key = f'buffer_tier_{tier}'
            if len(self.performance_stats[key]) > 100:
                self.performance_stats[key] = self.performance_stats[key][-100:]
                
        # Update memory usage history
        current_memory = self.process.memory_info().rss
        self.performance_stats['memory_usage'].append(current_memory)
        if len(self.performance_stats['memory_usage']) > 100:
            self.performance_stats['memory_usage'] = self.performance_stats['memory_usage'][-100:]
            
        # Update coordinator with latest metrics
        if self.coordinator:
            self.coordinator.update_performance_stats('signal_processor', {
                'processing_time': processing_time,
                'buffer_tier': 'small' if buffer_size <= 4 * 1024 else 'medium' if buffer_size <= 64 * 1024 else 'large',
                'buffer_size': buffer_size,
                'memory_usage': current_memory,
                'buffer_usage': {
                    'small': len(self.performance_stats['buffer_tier_small']),
                    'medium': len(self.performance_stats['buffer_tier_medium']),
                    'large': len(self.performance_stats['buffer_tier_large'])
                }
            })
        
    def safe_call(self, func_name: str, *args, **kwargs) -> Any:
        """Safely call audioop functions with error handling."""
        try:
            with self.memory_check():
                func = getattr(audioop, func_name)
                result = func(*args, **kwargs)
                return result
        except Exception as e:
            self.coordinator.logger.error(f"Audio processing error in {func_name}: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "signal_processor")
            return self.fallback_processing(func_name, *args, **kwargs)
            
    def fallback_processing(self, func_name: str, *args, **kwargs) -> Any:
        """Fallback processing using numpy when audioop fails."""
        if func_name == 'lin2lin':
            return self._fallback_lin2lin(*args)
        elif func_name == 'bias':
            return self._fallback_bias(*args)
        elif func_name == 'avg':
            return self._fallback_avg(*args)
        elif func_name == 'rms':
            return self._fallback_rms(*args)
        elif func_name == 'findfit':
            return self._fallback_findfit(*args)
        raise NotImplementedError(f"No fallback for {func_name}")
        
    def _fallback_lin2lin(self, data: bytes, width1: int, width2: int) -> bytes:
        """Fallback implementation of lin2lin using numpy."""
        dtype1 = {1: np.int8, 2: np.int16, 4: np.int32}[width1]
        dtype2 = {1: np.int8, 2: np.int16, 4: np.int32}[width2]
        
        arr = np.frombuffer(data, dtype=dtype1)
        scaled = (arr.astype(np.float32) * (2**(8*width2-1)) / (2**(8*width1-1)))
        return scaled.astype(dtype2).tobytes()
        
    def _fallback_bias(self, data: bytes, width: int, bias: int) -> bytes:
        """Fallback implementation of bias using numpy."""
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
        arr = np.frombuffer(data, dtype=dtype)
        biased = arr + bias
        return biased.astype(dtype).tobytes()
        
    def _fallback_avg(self, data: bytes, width: int) -> int:
        """Fallback implementation of avg using numpy."""
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
        arr = np.frombuffer(data, dtype=dtype)
        return int(np.mean(np.abs(arr)))
        
    def _fallback_rms(self, data: bytes, width: int) -> int:
        """Fallback implementation of rms using numpy."""
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
        arr = np.frombuffer(data, dtype=dtype)
        return int(np.sqrt(np.mean(arr.astype(np.float32)**2)))
        
    def _fallback_findfit(self, data1: bytes, data2: bytes) -> Tuple[int, float]:
        """Fallback implementation of findfit using numpy."""
        arr1 = np.frombuffer(data1, dtype=np.int16)
        arr2 = np.frombuffer(data2, dtype=np.int16)
        
        if len(arr1) > len(arr2):
            arr1 = arr1[:len(arr2)]
        else:
            arr2 = arr2[:len(arr1)]
            
        correlation = np.correlate(arr1, arr2, mode='full')
        offset = np.argmax(correlation) - len(arr1) + 1
        factor = float(np.max(correlation) / np.sum(arr1**2))
        
        return offset, factor
        
    async def cleanup(self) -> None:
        """Clean up signal processor resources."""
        try:
            if self.coordinator:
                self.coordinator.update_state(cleanup_started=True)
                
            # Clear performance stats
            self.performance_stats['processing_time'].clear()
            self.performance_stats['queue_size'].clear()
            self.performance_stats['sync_offsets'].clear()
            self.performance_stats['memory_usage'].clear()
            self.performance_stats['buffer_tier_small'].clear()
            self.performance_stats['buffer_tier_medium'].clear()
            self.performance_stats['buffer_tier_large'].clear()
            
            # Reset state
            self.processing_queue_size = 0
            self.processing_load = 0.0
            self._is_recovering = False
            self._last_channel_state = None
            self._processing_start_time = None
            
            # Clear history
            self.stats_history.clear()
            
            # Run garbage collection
            gc.collect()
            
            if self.coordinator:
                self.coordinator.update_state(cleanup_complete=True)
                
        except Exception as e:
            if self.coordinator:
                self.coordinator.logger.error(f"Error during signal processor cleanup: {e}")
                self.coordinator.handle_error(e, "signal_processor")
