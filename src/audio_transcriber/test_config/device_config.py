"""
Device configuration and simulation helpers for audio testing.
Provides standardized test device configurations and simulation utilities.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List, Set
import pyaudiowpatch as pyaudio
from enum import Enum, auto
import logging
import time
from contextlib import contextmanager

class DeviceType(Enum):
    """Types of audio devices used in testing."""
    SYSTEM_LOOPBACK = auto()
    VB_CABLE = auto()
    DEFAULT_OUTPUT = auto()
    DEFAULT_INPUT = auto()

@dataclass
class DeviceConfig:
    """Configuration for a test audio device."""
    device_type: DeviceType
    device_index: int
    name: str
    channels: int
    sample_rate: int
    format: int
    is_loopback: bool
    expected_latency: float
    
    def to_dict(self) -> Dict:
        """Convert config to dictionary for logging."""
        return {
            'device_type': self.device_type.name,
            'device_index': self.device_index,
            'name': self.name,
            'channels': self.channels,
            'sample_rate': self.sample_rate,
            'format': self.format,
            'is_loopback': self.is_loopback,
            'expected_latency': self.expected_latency
        }

class DeviceManager:
    """Manages audio device configurations and validation."""
    
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.configs: Dict[DeviceType, DeviceConfig] = {}
        self.active_streams: Set[pyaudio.Stream] = set()
        self._initialize_devices()
        
    def _find_device_by_name(self, name_pattern: str) -> Optional[Dict]:
        """Find a device by name pattern."""
        for i in range(self.pa.get_device_count()):
            try:
                info = self.pa.get_device_info_by_index(i)
                if name_pattern.lower() in info['name'].lower():
                    return info
            except Exception as e:
                logging.warning(f"Error getting device info for index {i}: {e}")
        return None

    def _initialize_devices(self):
        """Initialize and validate all required test devices with fallbacks."""
        try:
            # Find system loopback device (required)
            loopback_info = self._find_device_by_name('loopback')
            if not loopback_info:
                raise RuntimeError("Required system loopback device not found. Please ensure WASAPI loopback is enabled.")
                
            self.configs[DeviceType.SYSTEM_LOOPBACK] = DeviceConfig(
                device_type=DeviceType.SYSTEM_LOOPBACK,
                device_index=loopback_info['index'],
                name=loopback_info['name'],
                channels=loopback_info['maxInputChannels'],
                sample_rate=int(loopback_info['defaultSampleRate']),
                format=pyaudio.paFloat32,
                is_loopback=True,
                expected_latency=0.1
            )

            # Find VB-Cable device (required)
            vb_info = self._find_device_by_name('cable output')
            if not vb_info:
                raise RuntimeError("Required VB-Cable device not found. Please install VB-Cable from https://vb-audio.com/Cable/")
                
            self.configs[DeviceType.VB_CABLE] = DeviceConfig(
                device_type=DeviceType.VB_CABLE,
                device_index=vb_info['index'],
                name=vb_info['name'],
                channels=vb_info['maxInputChannels'],
                sample_rate=int(vb_info['defaultSampleRate']),
                format=pyaudio.paFloat32,
                is_loopback=False,
                expected_latency=0.05
            )

            # Add default devices with error handling
            try:
                default_output = self.pa.get_default_output_device_info()
                self.configs[DeviceType.DEFAULT_OUTPUT] = DeviceConfig(
                    device_type=DeviceType.DEFAULT_OUTPUT,
                    device_index=default_output['index'],
                    name=default_output['name'],
                    channels=default_output['maxOutputChannels'],
                    sample_rate=int(default_output['defaultSampleRate']),
                    format=pyaudio.paFloat32,
                    is_loopback=False,
                    expected_latency=0.2
                )
            except Exception as e:
                logging.error(f"Failed to get default output device: {e}")

            try:
                default_input = self.pa.get_default_input_device_info()
                self.configs[DeviceType.DEFAULT_INPUT] = DeviceConfig(
                    device_type=DeviceType.DEFAULT_INPUT,
                    device_index=default_input['index'],
                    name=default_input['name'],
                    channels=default_input['maxInputChannels'],
                    sample_rate=int(default_input['defaultSampleRate']),
                    format=pyaudio.paFloat32,
                    is_loopback=False,
                    expected_latency=0.2
                )
            except Exception as e:
                logging.error(f"Failed to get default input device: {e}")

            # Log available devices
            self._log_device_configs()

        except Exception as e:
            raise RuntimeError(f"Failed to initialize audio devices: {e}")

    def _log_device_configs(self):
        """Log all available device configurations."""
        for device_type, config in self.configs.items():
            logging.info(f"Initialized {device_type.name}: {config.to_dict()}")

    def get_config(self, device_type: DeviceType) -> DeviceConfig:
        """Get configuration for a specific device type with validation."""
        if device_type not in self.configs:
            available = ', '.join(d.name for d in self.configs.keys())
            raise ValueError(
                f"Device type {device_type} not found. Available devices: {available}"
            )
        return self.configs[device_type]

    def get_all_configs(self) -> List[DeviceConfig]:
        """Get configurations for all available devices."""
        return list(self.configs.values())

    @contextmanager
    def open_test_stream(self, config: DeviceConfig):
        """Safely open and manage a test stream."""
        stream = None
        try:
            stream = self.pa.open(
                format=config.format,
                channels=config.channels,
                rate=config.sample_rate,
                input=True,
                input_device_index=config.device_index,
                frames_per_buffer=1024
            )
            self.active_streams.add(stream)
            stream.start_stream()
            yield stream
        finally:
            if stream:
                try:
                    if stream.is_active():
                        stream.stop_stream()
                    stream.close()
                    self.active_streams.remove(stream)
                except Exception as e:
                    logging.error(f"Error closing test stream: {e}")

    def validate_device(self, device_type: DeviceType) -> bool:
        """Validate that a device is available and functioning with detailed checks."""
        try:
            config = self.get_config(device_type)
            
            # Test stream creation and basic functionality
            with self.open_test_stream(config) as stream:
                if not stream.is_active():
                    logging.error(f"Stream not active for {device_type.name}")
                    return False
                
                # Test basic audio flow
                time.sleep(0.1)  # Allow time for buffer to fill
                if not stream.get_read_available() > 0:
                    logging.error(f"No data available from {device_type.name}")
                    return False
                
                return True
                
        except Exception as e:
            logging.error(f"Device validation failed for {device_type.name}: {e}")
            return False

    def cleanup(self):
        """Clean up PyAudio resources with proper error handling."""
        cleanup_errors = []
        
        # Clean up active streams
        for stream in list(self.active_streams):
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
                self.active_streams.remove(stream)
            except Exception as e:
                cleanup_errors.append(f"Stream cleanup error: {e}")
        
        # Terminate PyAudio
        if hasattr(self, 'pa'):
            try:
                self.pa.terminate()
            except Exception as e:
                cleanup_errors.append(f"PyAudio termination error: {e}")
        
        # Log any cleanup errors
        if cleanup_errors:
            error_msg = '\n'.join(cleanup_errors)
            logging.error(f"Cleanup errors occurred:\n{error_msg}")
            raise RuntimeError(f"Device cleanup failed: {error_msg}")

class DeviceSimulator:
    """Simulates audio device behavior for testing."""

    @staticmethod
    def simulate_device_failure(device_config: DeviceConfig) -> Dict:
        """Simulate a device failure scenario."""
        return {
            'error_type': 'device_failure',
            'device_index': device_config.device_index,
            'name': device_config.name,
            'error_message': 'Simulated device failure',
            'timestamp': time.time()
        }

    @staticmethod
    def simulate_buffer_underrun(device_config: DeviceConfig) -> Dict:
        """Simulate a buffer underrun scenario."""
        return {
            'error_type': 'buffer_underrun',
            'device_index': device_config.device_index,
            'name': device_config.name,
            'error_message': 'Simulated buffer underrun',
            'timestamp': time.time()
        }

    @staticmethod
    def simulate_format_mismatch(device_config: DeviceConfig) -> Dict:
        """Simulate a format mismatch scenario."""
        return {
            'error_type': 'format_mismatch',
            'device_index': device_config.device_index,
            'name': device_config.name,
            'error_message': 'Simulated format mismatch',
            'timestamp': time.time()
        }

    @staticmethod
    def simulate_device_switch(old_config: DeviceConfig, new_config: DeviceConfig) -> Dict:
        """Simulate a device switch scenario."""
        return {
            'error_type': 'device_switch',
            'old_device': {
                'index': old_config.device_index,
                'name': old_config.name
            },
            'new_device': {
                'index': new_config.device_index,
                'name': new_config.name
            },
            'error_message': 'Simulated device switch',
            'timestamp': time.time()
        }
