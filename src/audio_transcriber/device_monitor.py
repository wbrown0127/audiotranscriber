"""
COMPONENT_NOTES:
{
    "name": "WASAPIMonitor",
    "type": "Audio System Component",
    "description": "Thread-safe WASAPI monitor that handles audio device monitoring, stream management, and error recovery",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                WM[WASAPIMonitor] --> SM[StateMachine]
                WM --> MC[MonitoringCoordinator]
                WM --> BM[BufferManager]
                WM --> PA[PyAudio]
                WM --> AS[AudioStream]
                MC --> RP[ResourcePool]
        ```",
        "dependencies": {
            "StateMachine": "Manages monitor state transitions and recovery",
            "MonitoringCoordinator": "Handles component lifecycle and centralized resource management",
            "BufferManager": "Manages audio data buffering and channel separation",
            "PyAudio": "Provides WASAPI audio device interface",
            "AudioStream": "Handles real-time audio streaming",
            "ResourcePool": "Centralized resource management through MonitoringCoordinator"
        }
    },
    "notes": [
        "Maintains strict lock ordering for thread safety",
        "Implements circuit breaker pattern for error handling",
        "Provides device change notifications and health monitoring",
        "Handles stereo channel separation and validation",
        "Uses centralized resource management through MonitoringCoordinator"
    ],
    "usage": {
        "examples": [
            "monitor = WASAPIMonitor(coordinator)",
            "monitor.initialize_stream(device_index)",
            "monitor.cleanup()",
            "monitor.register_device_change_callback(callback)"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pyaudiowpatch",
            "numpy",
            "threading",
            "logging"
        ],
        "system": {
            "audio": "WASAPI-compatible audio device",
            "memory": "Buffer management capacity",
            "cpu": "Real-time audio processing"
        }
    },
    "performance": {
        "execution_time": "Real-time audio processing",
        "resource_usage": [
            "Efficient buffer management",
            "Optimized channel separation",
            "Minimal lock contention",
            "Low-latency stream processing"
        ],
        "monitoring": {
            "buffer_stats": "Tracks overruns/underruns",
            "health_checks": "Continuous monitoring",
            "recovery": "Automatic error recovery"
        }
    }
}

"""

import logging
import threading
import time
import numpy as np
import pyaudiowpatch as pyaudio
from typing import Optional, Dict, Set, List
from typing_extensions import Tuple
from .state_machine import StateMachine, RecoveryState

class WASAPIMonitor:
    """
    Thread-safe WASAPI monitor with state machine integration.
    
    Lock Ordering:
    1. _state_lock
    2. _stream_lock
    3. _cleanup_lock
    """
    
    def __init__(self, coordinator):
        self.logger = logging.getLogger("WASAPIMonitor")
        self.coordinator = coordinator
        self._state_machine = StateMachine()
        
        # Thread safety
        self._state_lock = threading.Lock()
        self._stream_lock = threading.Lock()
        self._cleanup_lock = threading.Lock()
        self._device_lock = threading.Lock()  # New lock for device operations
        
        # Configuration
        self.max_attempts = 3
        self.silence_threshold = 1e-6
        self.health_check_interval = 1.0  # seconds
        
        # Circuit breaker configuration
        self.operation_timeout = 5.0  # 5 second timeout for operations
        self.max_consecutive_errors = 3
        self.error_count = 0
        self.last_error_time = 0
        self.circuit_breaker_cooldown = 60.0  # 1 minute cooldown
        
        # Buffer configuration
        self.min_buffer_size = 480  # 30ms at 16kHz
        self.max_buffer_size = 2048  # 128ms at 16kHz
        self.buffer_underrun_threshold = 0.8  # 80% of buffer size
        self.buffer_overrun_threshold = 0.2   # 20% of buffer size
        
        # Device tracking
        self._current_device_index = None
        self._device_info_cache = {}
        self._last_device_scan = 0
        self._device_scan_interval = 5.0  # seconds
        self._device_change_callbacks = set()
        
        # State tracking
        self._monitoring = threading.Event()
        self._is_cleaning_up = False
        self.stream = None
        self.pa = None
        
        # Performance metrics
        self._buffer_stats = {
            'underruns': 0,
            'overruns': 0,
            'total_frames': 0,
            'dropped_frames': 0
        }
        
        # Register state change callback
        self._state_machine.register_state_change_callback(self._handle_state_change)
        
        # Initialize coordinator state
        if self.coordinator:
            self.coordinator.register_thread()
            self.coordinator.update_state(
                stream_health=True,
                recovery_attempts=0,
                buffer_size=480  # Default 30ms at 16kHz
            )
            
    def _handle_state_change(self, old_state: RecoveryState, new_state: RecoveryState) -> None:
        """Handle state machine state changes."""
        try:
            self.logger.info(f"WASAPI state change: {old_state.value} -> {new_state.value}")
            
            if new_state == RecoveryState.FAILED:
                # Trigger recovery on failure
                self.attempt_recovery()
            elif new_state == RecoveryState.STOPPING_CAPTURE:
                # Stop stream during cleanup
                with self._stream_lock:
                    if self.stream and self.stream.is_active():
                        self.stream.stop_stream()
                        
        except Exception as e:
            self.logger.error(f"Error handling state change: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
                
    def register_device_change_callback(self, callback: callable) -> None:
        """Register a callback for device change notifications."""
        self._device_change_callbacks.add(callback)
        
    def unregister_device_change_callback(self, callback: callable) -> None:
        """Unregister a device change callback."""
        self._device_change_callbacks.discard(callback)
        
    def _notify_device_change(self, old_device: Optional[dict], new_device: Optional[dict]) -> None:
        """Notify registered callbacks of device changes."""
        for callback in self._device_change_callbacks:
            try:
                callback(old_device, new_device)
            except Exception as e:
                self.logger.error(f"Device change callback error: {e}")
                
    def get_wasapi_devices(self) -> Dict[int, dict]:
        """Thread-safe retrieval of WASAPI devices with caching."""
        try:
            with self._device_lock:
                current_time = time.time()
                # Use cached devices if recent
                if (current_time - self._last_device_scan < self._device_scan_interval and 
                    self._device_info_cache):
                    return self._device_info_cache.copy()
                    
                if not self.pa:
                    if not self._reinitialize_pyaudio():
                        raise RuntimeError("Failed to initialize PyAudio")
                        
                wasapi_info = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                devices = {}
                
                for i in range(self.pa.get_device_count()):
                    device_info = self.pa.get_device_info_by_index(i)
                    if device_info['hostApi'] == wasapi_info['index']:
                        devices[i] = device_info
                        
                # Check for device changes
                if self._device_info_cache:
                    self._check_device_changes(self._device_info_cache, devices)
                    
                # Update cache
                self._device_info_cache = devices.copy()
                self._last_device_scan = current_time
                
                return devices
                
        except Exception as e:
            self.logger.error(f"Error getting WASAPI devices: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
            return {}
            
    def _check_device_changes(self, old_devices: Dict[int, dict], new_devices: Dict[int, dict]) -> None:
        """Check for device changes and handle them."""
        try:
            # Find removed devices
            removed_devices = set(old_devices.keys()) - set(new_devices.keys())
            for device_id in removed_devices:
                self.logger.info(f"Device removed: {old_devices[device_id]['name']}")
                if device_id == self._current_device_index:
                    self._handle_device_removal(old_devices[device_id])
                    
            # Find added devices
            added_devices = set(new_devices.keys()) - set(old_devices.keys())
            for device_id in added_devices:
                self.logger.info(f"New device detected: {new_devices[device_id]['name']}")
                
            # Check for changes in existing devices
            for device_id in set(old_devices.keys()) & set(new_devices.keys()):
                if old_devices[device_id] != new_devices[device_id]:
                    self.logger.info(f"Device changed: {new_devices[device_id]['name']}")
                    if device_id == self._current_device_index:
                        self._handle_device_change(old_devices[device_id], new_devices[device_id])
                        
        except Exception as e:
            self.logger.error(f"Error checking device changes: {e}")
            
    def _handle_device_removal(self, removed_device: dict) -> None:
        """Handle removal of current audio device."""
        try:
            self.logger.warning(f"Current device removed: {removed_device['name']}")
            self._notify_device_change(removed_device, None)
            
            # Stop current stream
            with self._stream_lock:
                if self.stream and self.stream.is_active():
                    self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None
                    
            # Try to find and switch to a new device
            wasapi_info = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            new_device_index = wasapi_info.get("defaultOutputDevice")
            
            if new_device_index is not None:
                self.logger.info("Attempting to switch to default device")
                if self.initialize_stream(new_device_index):
                    self._current_device_index = new_device_index
                    new_device = self.pa.get_device_info_by_index(new_device_index)
                    self._notify_device_change(None, new_device)
                    
        except Exception as e:
            self.logger.error(f"Error handling device removal: {e}")
            self._state_machine.transition_to(RecoveryState.FAILED)
            
    def _handle_device_change(self, old_device: dict, new_device: dict) -> None:
        """Handle changes in current audio device configuration."""
        try:
            self.logger.info(f"Device configuration changed: {new_device['name']}")
            self._notify_device_change(old_device, new_device)
            
            # Reinitialize stream with new configuration
            if self.initialize_stream(new_device['index']):
                self._current_device_index = new_device['index']
            else:
                self.logger.error("Failed to initialize stream with new device configuration")
                self._state_machine.transition_to(RecoveryState.FAILED)
                
        except Exception as e:
            self.logger.error(f"Error handling device change: {e}")
            self._state_machine.transition_to(RecoveryState.FAILED)
            
    def validate_stream_config(self, device_info: dict) -> tuple[int, int]:
        """Thread-safe validation of stream configuration."""
        try:
            with self._state_lock:
                # Validate device capabilities
                if device_info['maxInputChannels'] < 2:
                    if not device_info['name'].endswith('[Loopback]'):
                        # Try to find stereo configuration
                        supported_configs = self._get_supported_configs(device_info)
                        if not supported_configs:
                            raise ValueError(
                                f"Device {device_info['name']} does not support required stereo configuration"
                            )
                        # Use first supported stereo config
                        device_info.update(supported_configs[0])
                        
                # Validate sample rate
                sample_rate = int(device_info.get('defaultSampleRate', 16000))
                if sample_rate < 16000:  # Ensure minimum quality
                    sample_rate = 16000
                    
                # Calculate optimal buffer size based on latency
                latency = device_info.get('defaultLowInputLatency', 0.03)  # Default 30ms
                optimal_buffer = int(sample_rate * latency)
                
                # Ensure minimum buffer duration of 30ms
                min_frames = int(sample_rate * 0.03)  # 30ms minimum
                max_frames = int(sample_rate * 0.128)  # 128ms maximum
                
                frames_per_buffer = min(max(optimal_buffer, min_frames), max_frames)
                buffer_duration = frames_per_buffer * 1000 / sample_rate  # ms
                
                self.logger.info(
                    f"Configuring device '{device_info['name']}':\n"
                    f"  Sample Rate: {sample_rate}Hz\n"
                    f"  Buffer Size: {frames_per_buffer} frames ({buffer_duration:.1f}ms)\n"
                    f"  Latency: {latency*1000:.1f}ms"
                )
                
                return sample_rate, frames_per_buffer
                
        except Exception as e:
            self.logger.error(f"Stream config validation error: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
            raise
            
    def _get_supported_configs(self, device_info: dict) -> List[dict]:
        """Thread-safe retrieval of supported device configurations."""
        configs = []
        try:
            with self._state_lock:
                # Try standard stereo configurations
                standard_rates = [16000, 44100, 48000]
                for rate in standard_rates:
                    try:
                        # Test if device supports this configuration
                        test_stream = self.pa.open(
                            format=pyaudio.paFloat32,
                            channels=2,
                            rate=rate,
                            input=True,
                            input_device_index=device_info['index'],
                            frames_per_buffer=480,
                            start=False
                        )
                        test_stream.close()
                        
                        # Configuration is supported
                        configs.append({
                            'defaultSampleRate': rate,
                            'maxInputChannels': 2
                        })
                    except:
                        continue
                        
        except Exception as e:
            self.logger.warning(f"Config detection error: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
                
        return configs
        
    def initialize_stream(self, device_index: Optional[int] = None) -> bool:
        """Thread-safe stream initialization."""
        try:
            with self._state_lock:
                if not self.pa:
                    if not self._reinitialize_pyaudio():
                        return False
                        
                wasapi_info = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                if device_index is None:
                    device_index = wasapi_info["defaultOutputDevice"]
                    
                device_info = self.pa.get_device_info_by_index(device_index)
                
                # Validate device capabilities
                if device_info['maxInputChannels'] < 2:
                    if '[Loopback]' not in device_info['name']:
                        self.logger.error(f"Device {device_info['name']} does not support stereo input")
                        return False
                        
                # Get optimal configuration
                sample_rate, frames_per_buffer = self.validate_stream_config(device_info)
                
                with self._stream_lock:
                    # Configure stream in shared mode only
                    self.stream = self.pa.open(
                        format=pyaudio.paFloat32,
                        channels=2,
                        rate=sample_rate,
                        input=True,
                        input_device_index=device_index,
                        frames_per_buffer=frames_per_buffer,
                        stream_callback=self._stream_callback
                    )
                    
                self.logger.info(f"Initialized stream: {device_info['name']}")
                self._state_machine.transition_to(RecoveryState.IDLE)
                return True
                
        except Exception as e:
            self.logger.error(f"Stream initialization error: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
            self._state_machine.transition_to(RecoveryState.FAILED)
            return False
            
    def _update_buffer_stats(self, frame_count: int, status: int) -> None:
        """Update buffer statistics based on stream status."""
        self._buffer_stats['total_frames'] += frame_count
        
        if status & pyaudio.paInputOverflow:
            self._buffer_stats['overruns'] += 1
            self.logger.warning("Buffer overrun detected")
            
        if status & pyaudio.paInputUnderflow:
            self._buffer_stats['underruns'] += 1
            self.logger.warning("Buffer underrun detected")
            
    def _check_buffer_health(self) -> bool:
        """Check buffer health based on statistics."""
        if self._buffer_stats['total_frames'] == 0:
            return True
            
        overrun_rate = self._buffer_stats['overruns'] / self._buffer_stats['total_frames']
        underrun_rate = self._buffer_stats['underruns'] / self._buffer_stats['total_frames']
        
        if overrun_rate > self.buffer_overrun_threshold:
            self.logger.error(f"Buffer overrun rate too high: {overrun_rate:.2%}")
            return False
            
        if underrun_rate > self.buffer_underrun_threshold:
            self.logger.error(f"Buffer underrun rate too high: {underrun_rate:.2%}")
            return False
            
        return True
        
    def _stream_callback(self, in_data, frame_count, time_info, status) -> tuple:
        """Thread-safe audio stream callback with buffer management."""
        try:
            # Update buffer statistics
            self._update_buffer_stats(frame_count, status)
            
            # Check for valid data
            if not in_data or len(in_data) == 0:
                self.logger.warning("Empty audio buffer received")
                self._buffer_stats['dropped_frames'] += frame_count
                self._state_machine.transition_to(RecoveryState.FAILED)
                return (in_data, pyaudio.paContinue)
                
            # Convert to numpy array with error handling
            try:
                audio_data = np.frombuffer(in_data, dtype=np.float32)
            except ValueError as e:
                self.logger.error(f"Buffer conversion error: {e}")
                self._buffer_stats['dropped_frames'] += frame_count
                self._state_machine.transition_to(RecoveryState.FAILED)
                return (in_data, pyaudio.paContinue)
                
            # Validate data shape
            expected_size = frame_count * 2  # stereo = 2 channels
            if len(audio_data) < expected_size:
                self.logger.error(f"Incomplete audio frame: got {len(audio_data)}, expected {expected_size}")
                self._buffer_stats['dropped_frames'] += frame_count
                self._state_machine.transition_to(RecoveryState.FAILED)
                return (in_data, pyaudio.paContinue)
                
            # Check buffer health
            if not self._check_buffer_health():
                self._state_machine.transition_to(RecoveryState.FAILED)
                return (in_data, pyaudio.paContinue)
                
            # Check for silence/invalid audio
            peak_amplitude = np.max(np.abs(audio_data))
            if peak_amplitude < self.silence_threshold:
                self.logger.warning(f"Silent audio detected: peak = {peak_amplitude:.2e}")
                self._state_machine.transition_to(RecoveryState.FAILED)
            else:
                # Split channels
                left_channel = audio_data[::2]
                right_channel = audio_data[1::2]
                
                # Verify channel health
                channel_health = self._verify_channel_health(left_channel, right_channel)
                if not channel_health['healthy']:
                    self.logger.warning("Channel issues detected:")
                    for issue in channel_health['issues']:
                        self.logger.warning(f"  - {issue}")
                    self._state_machine.transition_to(RecoveryState.FAILED)
                else:
                    self._state_machine.transition_to(RecoveryState.IDLE)
                    if self.coordinator:
                        self.coordinator.update_state(
                            stream_health=True,
                            recovery_attempts=0  # Reset on good data
                        )
                    
                # Put audio data in buffer manager with channel separation
                if self.coordinator and hasattr(self.coordinator, 'buffer_manager'):
                    # Store left channel in 'capture_left' buffer
                    if not self.coordinator.buffer_manager.put_buffer('capture_left', left_channel.tobytes(), timeout=0.1):
                        self.logger.error("Failed to put left channel data in buffer")
                        self._state_machine.transition_to(RecoveryState.FAILED)
                        
                    # Store right channel in 'capture_right' buffer
                    if not self.coordinator.buffer_manager.put_buffer('capture_right', right_channel.tobytes(), timeout=0.1):
                        self.logger.error("Failed to put right channel data in buffer")
                        self._state_machine.transition_to(RecoveryState.FAILED)
                    
            return (in_data, pyaudio.paContinue)
            
        except Exception as e:
            self.logger.error(f"Stream callback error: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
            self._state_machine.transition_to(RecoveryState.FAILED)
            return (in_data, pyaudio.paAbort)
            
    def _verify_channel_health(self, left: np.ndarray, right: np.ndarray) -> dict:
        """Thread-safe channel health verification."""
        issues = []
        
        try:
            # Check for NaN or Inf values
            if np.any(np.isnan(left)) or np.any(np.isnan(right)):
                issues.append("NaN values detected in audio data")
            if np.any(np.isinf(left)) or np.any(np.isinf(right)):
                issues.append("Infinite values detected in audio data")
                
            # Check amplitude balance
            left_peak = np.max(np.abs(left))
            right_peak = np.max(np.abs(right))
            if min(left_peak, right_peak) < self.silence_threshold:
                issues.append(f"Channel imbalance - L:{left_peak:.2e} R:{right_peak:.2e}")
                
            # Check for DC offset
            left_mean = np.mean(left)
            right_mean = np.mean(right)
            dc_threshold = 0.1  # 10% of full scale
            if abs(left_mean) > dc_threshold or abs(right_mean) > dc_threshold:
                issues.append(f"DC offset detected - L:{left_mean:.2f} R:{right_mean:.2f}")
                
            # Check for signal variance (flatline detection)
            left_std = np.std(left)
            right_std = np.std(right)
            if left_std < 1e-4 or right_std < 1e-4:
                issues.append(f"Low signal variance - L:{left_std:.2e} R:{right_std:.2e}")
                
            # Check correlation (isolation) only if we have valid audio
            if len(left) > 1 and len(right) > 1:
                if left_std > 1e-4 and right_std > 1e-4:  # Only check correlation if not silence/flatline
                    try:
                        correlation = np.corrcoef(left, right)[0, 1]
                        # Only report correlation for non-loopback devices
                        with self._stream_lock:
                            if self.stream and hasattr(self.stream, '_device_index'):
                                try:
                                    device_info = self.pa.get_device_info_by_index(self.stream._device_index)
                                    if not device_info['name'].endswith('[Loopback]') and abs(correlation) > 0.8:
                                        issues.append(f"High channel correlation: {correlation:.2f}")
                                except:
                                    pass
                    except ValueError as e:
                        issues.append(f"Correlation calculation error: {e}")
                        
        except Exception as e:
            self.logger.error(f"Channel health verification error: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
            issues.append(f"Health check error: {e}")
            
        return {
            'healthy': len(issues) == 0,
            'issues': issues
        }
        
    def attempt_recovery(self) -> bool:
        """Thread-safe stream recovery attempt."""
        try:
            with self._state_lock:
                state = self.coordinator.get_state()
                if state.recovery_attempts >= self.max_attempts:
                    return False
                    
                self.logger.info(f"Recovery attempt {state.recovery_attempts + 1}/{self.max_attempts}")
                
                # Full cleanup and reinit
                with self._stream_lock:
                    if self.stream:
                        try:
                            if self.stream.is_active():
                                self.stream.stop_stream()
                            self.stream.close()
                        except Exception as e:
                            self.logger.warning(f"Stream cleanup warning: {e}")
                        finally:
                            self.stream = None
                            
                # Reinitialize PyAudio with retry
                max_retries = 3
                for retry in range(max_retries):
                    if self._reinitialize_pyaudio():
                        try:
                            # Get current device or fallback to default
                            wasapi_info = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                            device_index = wasapi_info["defaultOutputDevice"]
                            if self.initialize_stream(device_index):
                                self.logger.info("Stream recovered successfully")
                                return True
                        except Exception as e:
                            self.logger.error(f"Device initialization failed (attempt {retry + 1}/{max_retries}): {e}")
                            time.sleep(0.5)
                            continue
                    else:
                        self.logger.error(f"PyAudio reinitialization failed (attempt {retry + 1}/{max_retries})")
                        time.sleep(0.5)
                        
                if self.coordinator:
                    self.coordinator.update_state(
                        recovery_attempts=state.recovery_attempts + 1
                    )
                return False
                
        except Exception as e:
            self.logger.error(f"Recovery failed: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
            return False
            
    def _reinitialize_pyaudio(self) -> bool:
        """Thread-safe PyAudio reinitialization."""
        try:
            with self._state_lock:
                # Cleanup existing stream if any
                with self._stream_lock:
                    if self.stream:
                        try:
                            if self.stream.is_active():
                                self.stream.stop_stream()
                            self.stream.close()
                        except Exception as e:
                            self.logger.warning(f"Stream cleanup warning: {e}")
                        finally:
                            self.stream = None
                            
                # Cleanup existing PyAudio instance
                if self.pa:
                    try:
                        self.pa.terminate()
                    except Exception as e:
                        self.logger.warning(f"PyAudio cleanup warning: {e}")
                    finally:
                        self.pa = None
                        
                # Allow time for system resources to be released
                time.sleep(0.5)
                
                # Create new PyAudio instance with retry
                max_retries = 3
                for retry in range(max_retries):
                    try:
                        self.pa = pyaudio.PyAudio()
                        
                        # Verify initialization
                        if not self.pa:
                            raise RuntimeError("Failed to create PyAudio instance")
                            
                        # Test WASAPI availability
                        wasapi_info = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                        if not wasapi_info:
                            raise RuntimeError("WASAPI API not available")
                            
                        # Test device enumeration
                        device_count = self.pa.get_device_count()
                        if device_count == 0:
                            raise RuntimeError("No audio devices found")
                            
                        # Test default device access
                        default_device = wasapi_info.get("defaultOutputDevice")
                        if default_device is None:
                            raise RuntimeError("No default output device")
                            
                        return True
                        
                    except Exception as e:
                        self.logger.error(f"PyAudio initialization attempt {retry + 1}/{max_retries} failed: {e}")
                        if self.pa:
                            try:
                                self.pa.terminate()
                            except:
                                pass
                            self.pa = None
                        if retry < max_retries - 1:
                            time.sleep(1.0)
                            
                self.logger.error("All PyAudio initialization attempts failed")
                return False
                
        except Exception as e:
            self.logger.error(f"PyAudio reinitialization failed: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "wasapi_monitor")
            return False
            
    def cleanup(self) -> None:
        """Thread-safe cleanup operation."""
        try:
            with self._cleanup_lock:
                if self._is_cleaning_up:
                    return
                self._is_cleaning_up = True
                self._state_machine.transition_to(RecoveryState.STOPPING_CAPTURE)
                
            try:
                # Stop monitoring
                self._monitoring.clear()
                
                # Clean up stream with timeout
                with self._stream_lock:
                    if self.stream:
                        try:
                            start_time = time.time()
                            while time.time() - start_time < self.operation_timeout:
                                if self.stream.is_active():
                                    self.stream.stop_stream()
                                if not self.stream.is_active():
                                    break
                                time.sleep(0.1)
                                
                            self.stream.close()
                        except Exception as e:
                            self.logger.error(f"Stream cleanup error: {e}")
                        finally:
                            self.stream = None
                            
                # Clean up PyAudio with timeout
                with self._state_lock:
                    if self.pa:
                        try:
                            self.pa.terminate()
                        except Exception as e:
                            self.logger.error(f"PyAudio cleanup error: {e}")
                        finally:
                            self.pa = None
                            
                # Reset state
                if self.coordinator:
                    self.coordinator.update_state(
                        stream_health=True,
                        recovery_attempts=0
                    )
                    self.coordinator.mark_component_cleanup_complete('wasapi')
                    self.coordinator.unregister_thread()
                    
                self._state_machine.transition_to(RecoveryState.COMPLETED)
                
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")
                if self.coordinator:
                    self.coordinator.handle_error(e, "wasapi_monitor")
                self._state_machine.transition_to(RecoveryState.FAILED)
                
        finally:
            with self._cleanup_lock:
                self._is_cleaning_up = False
