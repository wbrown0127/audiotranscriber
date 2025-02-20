"""
COMPONENT_NOTES (Updated 2025-02-19):
- Removed direct BufferManager import and instantiation
- Now properly gets BufferManager through coordinator
- Uses proper accessor methods for buffer state and metrics
- Removed direct access to internal buffer queues
- Updated to use proper WASAPI monitor interfaces

{
    "name": "AdaptiveAudioCapture",
    "type": "Core Component",
    "description": "Advanced audio capture system with adaptive buffer management, performance monitoring, and WASAPI integration",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                AAC[AdaptiveAudioCapture] --> PM[PerformanceMonitor]
                AAC --> BM[BufferManager]
                AAC --> WM[WASAPIMonitor]
                PM --> CPU[CPUMonitor]
                PM --> TM[TempMonitor]
                BM --> BQ[BufferQueue]
                WM --> DS[DeviceState]
                WM --> BS[BufferStats]
                AAC --> AS[AudioStats]
        ```",
        "dependencies": {
            "PerformanceMonitor": "System resource monitoring",
            "BufferManager": "Audio buffer management",
            "WASAPIMonitor": "WASAPI device management",
            "AudioStats": "Audio metrics tracking",
            "CPUMonitor": "CPU usage monitoring",
            "TempMonitor": "Temperature monitoring",
            "BufferQueue": "Audio data queuing",
            "DeviceState": "Audio device tracking",
            "BufferStats": "Buffer performance metrics"
        }
    },
    "notes": [
        "Implements adaptive buffer sizing based on system load",
        "Provides real-time performance monitoring",
        "Handles device changes and failures gracefully",
        "Manages stereo channel separation",
        "Tracks audio quality metrics",
        "Supports WASAPI device enumeration"
    ],
    "usage": {
        "examples": [
            "capture = AdaptiveAudioCapture(coordinator)",
            "capture.start_capture()",
            "stats = capture.get_performance_stats()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pyaudiowpatch",
            "numpy",
            "psutil"
        ],
        "system": {
            "os": "Windows 10/11",
            "audio": "WASAPI-compatible device"
        }
    },
    "performance": {
        "execution_time": "Real-time audio processing",
        "resource_usage": [
            "Adaptive CPU usage based on load",
            "Dynamic buffer management",
            "Efficient channel processing",
            "Minimal latency overhead"
        ]
    }
}
"""

import pyaudiowpatch as pyaudio
import numpy as np
import threading
import time
import psutil
from typing import Optional, Dict, Any, List, Set
from queue import Queue
from dataclasses import dataclass

@dataclass
class AudioStats:
    peak: float
    rms: float
    sample_width: int
    channels: int

class PerformanceMonitor:
    def __init__(self):
        self.cpu_threshold = 80  # 80% CPU usage trigger
        self.temp_threshold = 85  # 85°C temperature trigger
        self.buffer_sizes = [480, 960, 1440]  # 30ms, 60ms, 90ms
        self.current_buffer_idx = 0
        self.last_adjustment = 0  # Initialize to 0 to allow first adjustment
        self.cooldown_period = 60  # 1 minute between adjustments

    def reset_cooldown(self):
        """Reset the cooldown timer. Primarily used for testing."""
        self.last_adjustment = 0
        
    def get_cpu_stats(self) -> tuple[float, Optional[float]]:
        """Get current CPU usage and temperature."""
        cpu_usage = psutil.cpu_percent(interval=1)
        try:
            temp = psutil.sensors_temperatures()['coretemp'][0].current
        except (AttributeError, KeyError):
            temp = None
        return cpu_usage, temp
        
    def should_adjust(self, cpu_usage: float, temp: Optional[float]) -> bool:
        """Determine if buffer adjustment is needed."""
        if time.time() - self.last_adjustment < self.cooldown_period:
            return False
        
        if cpu_usage > self.cpu_threshold:
            return True
            
        if temp and temp > self.temp_threshold:
            return True
            
        return False
        
    def adjust_buffer_size(self) -> Optional[int]:
        """Adjust buffer size based on performance metrics."""
        if self.current_buffer_idx < len(self.buffer_sizes) - 1:
            self.current_buffer_idx += 1
            self.last_adjustment = time.time()
            return self.buffer_sizes[self.current_buffer_idx]
        return None

class AdaptiveAudioCapture:
    """Main audio capture interface providing high-level capture functionality."""
    
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.monitor = PerformanceMonitor()
        # Get buffer manager from coordinator
        self.buffer_manager = coordinator.get_buffer_manager()
        if self.buffer_manager is None:
            raise RuntimeError("BufferManager not available from coordinator")
            
        # Initialize WASAPI monitor for device management
        # Get WASAPI monitor from coordinator
        self.wasapi_monitor = coordinator.get_wasapi_monitor()
        if self.wasapi_monitor is None:
            raise RuntimeError("WASAPIMonitor not available from coordinator")
            
        self.is_running = False
        self.stats_history = []
        self.wasapi = self  # For backward compatibility with tests
        self.stream = None
        self.pa = None
        self.stream_health = True
        self.recovery_attempts = 0
        self.silence_threshold = 1e-6
        
        # Register for device change notifications
        self.wasapi_monitor.register_device_change_callback(self._handle_device_change)

        # Initialize buffer configuration
        self.buffer_manager.update_buffer_config(
            size=self.monitor.buffer_sizes[0],  # Start with smallest buffer
            channels=2,
            sample_width=4,  # Using paFloat32
            sample_rate=16000
        )

        # Initialize state attributes
        if self.coordinator:
            self.coordinator.update_state(
                stream_health=True,
                recovery_attempts=0,
                buffer_size=self.monitor.buffer_sizes[0],
                capture_queue_size=0,
                capture_buffer_size=0
            )

    def _handle_device_change(self, old_device: Optional[dict], new_device: Optional[dict]) -> None:
        """Handle device change notifications from WASAPIMonitor."""
        try:
            if old_device and not new_device:
                # Device removed
                self.coordinator.logger.warning(f"Audio device removed: {old_device.get('name', 'Unknown')}")
                if self.is_running:
                    # Stop current capture
                    self.stop_capture()
                    # Try to find and switch to a new device
                    if self.start_capture():
                        self.coordinator.logger.info("Successfully switched to new audio device")
                    else:
                        self.coordinator.logger.error("Failed to switch to new audio device")
                        
            elif new_device and not old_device:
                # New device added
                self.coordinator.logger.info(f"New audio device detected: {new_device.get('name', 'Unknown')}")
                
            elif old_device and new_device:
                # Device configuration changed
                self.coordinator.logger.info(f"Audio device configuration changed: {new_device.get('name', 'Unknown')}")
                if self.is_running:
                    # Reinitialize stream with new configuration
                    self.stop_capture()
                    if self.start_capture():
                        self.coordinator.logger.info("Successfully reinitialized with new configuration")
                    else:
                        self.coordinator.logger.error("Failed to reinitialize with new configuration")
                        
        except Exception as e:
            self.coordinator.logger.error(f"Error handling device change: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "audio_capture")

    def _stream_callback(self, in_data, frame_count, time_info, status) -> tuple:
        """Process incoming audio data and monitor stream health."""
        try:
            # Update WASAPI buffer statistics
            self.wasapi_monitor.update_buffer_stats(frame_count, status)
            
            # Check WASAPI buffer health
            if not self.wasapi_monitor.check_buffer_health():
                self.coordinator.logger.warning("WASAPI buffer health check failed")
                self.coordinator.update_state(stream_health=False)
                return (in_data, pyaudio.paContinue)
            
            # Check for valid data
            if not in_data or len(in_data) == 0:
                self.coordinator.logger.warning("Empty audio buffer received")
                self.wasapi_monitor.increment_dropped_frames(frame_count)
                self.coordinator.update_state(stream_health=False)
                return (in_data, pyaudio.paContinue)
                
            # Convert to numpy array with error handling
            try:
                audio_data = np.frombuffer(in_data, dtype=np.float32)
            except ValueError as e:
                self.coordinator.logger.error(f"Buffer conversion error: {e}")
                self.wasapi_monitor.increment_dropped_frames(frame_count)
                self.coordinator.update_state(stream_health=False)
                return (in_data, pyaudio.paContinue)
                
            # Validate data shape
            expected_size = frame_count * 2  # stereo = 2 channels
            if len(audio_data) < expected_size:
                self.coordinator.logger.warning(f"Incomplete audio frame: got {len(audio_data)}, expected {expected_size}")
                self.wasapi_monitor.increment_dropped_frames(frame_count)
                self.coordinator.update_state(stream_health=False)
                return (in_data, pyaudio.paContinue)
                
            # Check for silence/invalid audio
            peak_amplitude = np.max(np.abs(audio_data))
            if peak_amplitude < self.silence_threshold:
                self.coordinator.logger.debug(f"Silent audio detected: peak = {peak_amplitude:.2e}")
                self.coordinator.update_state(stream_health=False)
            else:
                # Split channels
                left_channel = audio_data[::2]
                right_channel = audio_data[1::2]
                
                # Verify channel health using WASAPIMonitor
                channel_health = self.wasapi_monitor.verify_channel_health(left_channel, right_channel)
                if not channel_health['healthy']:
                    self.coordinator.logger.warning("Channel issues detected:")
                    for issue in channel_health['issues']:
                        self.coordinator.logger.warning(f"  - {issue}")
                    self.coordinator.update_state(stream_health=False)
                else:
                    self.coordinator.update_state(
                        stream_health=True,
                        recovery_attempts=0  # Reset on good data
                    )
                    
            # Put audio data in buffer manager (split into left and right channels)
            left_channel = audio_data[::2].tobytes()
            right_channel = audio_data[1::2].tobytes()
            
            # Put both channels in their respective buffers with timeout
            if (self.buffer_manager.put_buffer('capture_left', left_channel, timeout=0.1) and
                self.buffer_manager.put_buffer('capture_right', right_channel, timeout=0.1)):
                # Get queue sizes through proper methods
                buffer_state = self.buffer_manager.get_state()
                left_queue = buffer_state.get('capture_left_queue_size', 0)
                right_queue = buffer_state.get('capture_right_queue_size', 0)
                
                # Update buffer stats
                if max(left_queue, right_queue) > self.wasapi_monitor.buffer_overrun_threshold:
                    self.wasapi_monitor.increment_overruns()
                elif max(left_queue, right_queue) < self.wasapi_monitor.buffer_underrun_threshold:
                    self.wasapi_monitor.increment_underruns()
                
                self.coordinator.update_state(
                    capture_queue_size=max(left_queue, right_queue),
                    capture_buffer_size=len(in_data)
                )
                return (in_data, pyaudio.paContinue)
            else:
                self.coordinator.logger.error("Failed to put audio data in buffer")
                self.wasapi_monitor.increment_dropped_frames(frame_count)
                self.coordinator.update_state(stream_health=False)
                return (in_data, pyaudio.paContinue)
            
        except Exception as e:
            self.coordinator.logger.error(f"Stream callback error: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "audio_capture")
            self.stream_health = False
            return (in_data, pyaudio.paAbort)

    def _verify_channel_health(self, left: np.ndarray, right: np.ndarray) -> dict:
        """Comprehensive channel health verification."""
        return self.wasapi_monitor.verify_channel_health(left, right)

    def get_devices(self) -> Dict[int, dict]:
        """Get available WASAPI devices using WASAPIMonitor."""
        return self.wasapi_monitor.get_wasapi_devices()

    def initialize_stream(self, device_index: Optional[int] = None) -> bool:
        """Initialize WASAPI stream with error handling and recovery."""
        return self.wasapi_monitor.initialize_stream(device_index)

    def start_capture(self) -> bool:
        """Start audio capture with monitoring."""
        try:
            # Initialize stream with default device if not already initialized
            if not self.stream:
                if not self.initialize_stream():
                    return False
            
            self.is_running = True
            return True
            
        except Exception as e:
            if self.coordinator:
                self.coordinator.logger.error(f"Capture start error: {e}")
            return False

    def _cleanup_stream(self):
        """Clean up stream resources with verification."""
        self.wasapi_monitor.cleanup_stream()

    def stop_capture(self):
        """Stop audio capture and cleanup with verification."""
        self.is_running = False
        self.wasapi_monitor.cleanup()

    def get_performance_stats(self) -> dict:
        """Get current performance statistics with integrated WASAPI monitoring."""
        # Get CPU and temperature stats
        cpu_usage, temp = self.monitor.get_cpu_stats()
        state = self.coordinator.get_state()
        
        # Check if we need to adjust buffer size
        if self.monitor.should_adjust(cpu_usage, temp):
            new_size = self.monitor.adjust_buffer_size()
            if new_size:
                self.buffer_manager.update_buffer_config(size=new_size)
                
        # Get buffer stats from both managers
        buffer_stats = self.buffer_manager.get_performance_stats()
        wasapi_stats = self.wasapi_monitor.get_buffer_stats()
        
        # Get queue sizes through proper methods
        buffer_state = self.buffer_manager.get_state()
        left_queue = buffer_state.get('capture_left_queue_size', 0)
        right_queue = buffer_state.get('capture_right_queue_size', 0)
        capture_queue_size = max(left_queue, right_queue)  # Use max of left/right channels
        
        # Combine stats
        stats = {
            'cpu_usage': cpu_usage,
            'temperature': temp,
            'buffer_size': self.buffer_manager.get_buffer_config().size,
            'buffer_duration_ms': self.buffer_manager.get_buffer_config().duration_ms,
            'stream_health': state.stream_health,
            'recovery_attempts': state.recovery_attempts,
            'capture_queue_size': capture_queue_size,
            # Add WASAPI buffer stats
            'buffer_overruns': wasapi_stats.get('overruns', 0),
            'buffer_underruns': wasapi_stats.get('underruns', 0),
            'total_frames': wasapi_stats.get('total_frames', 0),
            'dropped_frames': wasapi_stats.get('dropped_frames', 0)
        }
        
        # Update coordinator with latest stats
        if self.coordinator:
            self.coordinator.update_performance_stats('capture', stats)
            
        return stats
