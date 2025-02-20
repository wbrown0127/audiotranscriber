"""
COMPONENT_NOTES:
{
    "name": "SpeakerIsolation",
    "type": "Core Component",
    "description": "Speaker isolation system that manages audio channel separation, speech detection, and speaker profiling through MonitoringCoordinator with thread-safe memory management",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                SI[SpeakerIsolation] --> MC[MonitoringCoordinator]
                SI --> SS[SpeakerSegment]
                SI --> SP[SpeakerProfile]
                SI --> CS[ChannelSeparator]
                SI --> SD[SpeechDetector]
                MC --> RP[ResourcePool]
                MC --> CC[ComponentCoordinator]
                CS --> AB[AudioBuffer]
                SD --> EL[EnergyLevel]
                SP --> SF[SpectralFeatures]
                SP --> FFT[FFTProcessor]
                SI --> PM[PerformanceMetrics]
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
            "SpeakerSegment": {
                "description": "Speech segment data structure",
                "responsibilities": [
                    "Segment timing",
                    "Channel tracking",
                    "Audio data storage",
                    "Confidence scoring"
                ]
            },
            "SpeakerProfile": {
                "description": "Speaker characteristics tracking",
                "responsibilities": [
                    "Profile maintenance",
                    "Feature extraction",
                    "Speaker identification",
                    "Profile updates"
                ]
            },
            "ChannelSeparator": {
                "description": "Audio channel handling",
                "responsibilities": [
                    "Channel isolation",
                    "Buffer management",
                    "Data validation",
                    "Error recovery"
                ]
            },
            "SpeechDetector": {
                "description": "Speech detection system",
                "responsibilities": [
                    "Energy analysis",
                    "Segment detection",
                    "Threshold management",
                    "Noise filtering"
                ]
            }
        }
    },
    "notes": [
        "Manages thread-safe audio processing",
        "Implements efficient buffer management",
        "Provides speaker detection and isolation",
        "Supports multi-channel audio",
        "Tracks speaker profiles",
        "Ensures proper resource cleanup"
    ],
    "usage": {
        "examples": [
            "isolator = SpeakerIsolation(coordinator)",
            "segments = isolator.process_audio_chunk(audio_data)",
            "stats = isolator.get_speaker_stats()",
            "await isolator.cleanup()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "numpy",
            "audioop",
            "typing_extensions"
        ],
        "system": {
            "memory": "Managed through MonitoringCoordinator",
            "cpu": "FFT processing capability"
        }
    },
    "performance": {
        "execution_time": "Real-time audio processing",
        "resource_usage": [
            "Efficient buffer reuse",
            "Optimized FFT calculations",
            "Thread-safe operations",
            "Minimal memory allocation"
        ]
    }
}
"""

import numpy as np
import logging
from typing import List, Dict, Optional
from typing_extensions import Tuple
from dataclasses import dataclass
import audioop
logger = logging.getLogger(__name__)

@dataclass
class SpeakerSegment:
    """Represents an isolated segment of speech from a specific speaker."""
    speaker_id: str
    start_time: float
    end_time: float
    channel: int
    confidence: float
    audio_data: bytes

class SpeakerIsolation:
    """Handles speaker isolation and channel separation for audio transcription."""
    
    def __init__(self, 
                 coordinator=None,
                 sample_rate: int = 16000,
                 channels: int = 2,
                 energy_threshold: float = 0.1,
                 min_segment_duration: float = 0.5):
        """
        Initialize speaker isolation system.
        
        Args:
            coordinator: ComponentCoordinator for resource management
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels
            energy_threshold: Minimum energy level to detect speech
            min_segment_duration: Minimum duration for a valid speech segment
        """
        self.coordinator = coordinator
        self.sample_rate = sample_rate
        self.channels = channels
        self.energy_threshold = energy_threshold
        self.min_samples = int(min_segment_duration * sample_rate)
        self._speaker_profiles: Dict[str, np.ndarray] = {}
        self._current_segment: Optional[SpeakerSegment] = None
        
        # Register with coordinator
        if self.coordinator:
            self.coordinator.register_thread()
        
    def separate_channels(self, audio_chunk: bytes) -> List[bytes]:
        """
        Separate stereo audio into individual channel buffers using resource pool.
        
        Args:
            audio_chunk: Raw audio data (interleaved channels)
            
        Returns:
            List of separated channel buffers
        """
        if not self.coordinator:
            return [audio_chunk] * self.channels
            
        try:
            # Convert to numpy array for processing
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            
            # Allocate buffers through coordinator
            channel_size = len(audio_array) // self.channels
            channel_buffers = []
            
            for i in range(self.channels):
                # Allocate buffer for this channel
                buffer = self.coordinator.allocate_resource('speaker_isolation', 'buffer', channel_size * 2)
                if not buffer:
                    self.coordinator.logger.error(f"Failed to allocate buffer for channel {i}")
                    raise RuntimeError(f"Failed to allocate buffer for channel {i}")
                
                try:
                    # Extract channel data
                    channel = audio_array[i::self.channels]
                    # Copy to buffer
                    np.copyto(np.frombuffer(buffer, dtype=np.int16), channel)
                    channel_buffers.append(buffer)
                except Exception as e:
                    # Release buffer on error
                    self.coordinator.release_resource('speaker_isolation', 'buffer', buffer)
                    raise
            
            return channel_buffers
            
        except Exception as e:
            self.coordinator.logger.error(f"Channel separation error: {e}")
            self.coordinator.handle_error(e, "speaker_isolation")
            # Return original audio in both channels as fallback
            return [audio_chunk] * self.channels
            
    def detect_speech_segments(self, 
                             channel_data: bytes,
                             channel_index: int) -> List[SpeakerSegment]:
        """
        Detect speech segments in a single channel.
        
        Args:
            channel_data: Audio data for one channel
            channel_index: Index of the channel being processed
            
        Returns:
            List of detected speech segments
        """
        if not self.coordinator:
            return []
            
        segments = []
        
        try:
            # Convert to numpy array
            audio_array = np.frombuffer(channel_data, dtype=np.int16)
            
            # Calculate energy levels
            frame_size = self.sample_rate // 100  # 10ms frames
            num_frames = len(audio_array) // frame_size
            
            segment_start = None
            current_audio = []
            
            for i in range(num_frames):
                frame = audio_array[i * frame_size:(i + 1) * frame_size]
                energy = np.mean(np.abs(frame)) / 32768.0  # Normalize to 0-1
                
                if energy > self.energy_threshold:
                    if segment_start is None:
                        segment_start = i * frame_size / self.sample_rate
                    current_audio.extend(frame)
                elif segment_start is not None:
                    # End of speech segment
                    if len(current_audio) >= self.min_samples:
                        # Allocate buffer for segment
                        buffer = self.coordinator.allocate_resource('speaker_isolation', 'buffer', len(current_audio) * 2)
                        if buffer:
                            try:
                                # Copy segment data to buffer
                                np.copyto(np.frombuffer(buffer, dtype=np.int16), current_audio)
                                
                                segment = SpeakerSegment(
                                    speaker_id=f"speaker_{channel_index}",
                                    start_time=segment_start,
                                    end_time=i * frame_size / self.sample_rate,
                                    channel=channel_index,
                                    confidence=0.8,  # Default confidence
                                    audio_data=bytes(buffer)
                                )
                                segments.append(segment)
                            finally:
                                # Release buffer after copying data
                                self.coordinator.release_resource('speaker_isolation', 'buffer', buffer)
                    
                    segment_start = None
                    current_audio = []
            
            # Handle segment at end of buffer
            if segment_start is not None and len(current_audio) >= self.min_samples:
                # Allocate buffer for final segment
                buffer = self.coordinator.allocate_resource('speaker_isolation', 'buffer', len(current_audio) * 2)
                if buffer:
                    try:
                        # Copy segment data to buffer
                        np.copyto(np.frombuffer(buffer, dtype=np.int16), current_audio)
                        
                        segment = SpeakerSegment(
                            speaker_id=f"speaker_{channel_index}",
                            start_time=segment_start,
                            end_time=len(audio_array) / self.sample_rate,
                            channel=channel_index,
                            confidence=0.8,
                            audio_data=bytes(buffer)
                        )
                        segments.append(segment)
                    finally:
                        # Release buffer after copying data
                        self.coordinator.release_resource('speaker_isolation', 'buffer', buffer)
                
            return segments
            
        except Exception as e:
            self.coordinator.logger.error(f"Speech detection error: {e}")
            self.coordinator.handle_error(e, "speaker_isolation")
            return []
            
    def update_speaker_profile(self, segment: SpeakerSegment) -> None:
        """
        Update speaker profile based on new speech segment.
        
        Args:
            segment: Speech segment to analyze
        """
        if not self.coordinator:
            return
            
        try:
            # Allocate buffer for FFT
            buffer = self.coordinator.allocate_resource('speaker_isolation', 'buffer', len(segment.audio_data))
            if not buffer:
                self.coordinator.logger.error("Failed to allocate buffer for speaker profile update")
                return
                
            try:
                # Copy segment data to buffer
                np.copyto(np.frombuffer(buffer, dtype=np.int16), np.frombuffer(segment.audio_data, dtype=np.int16))
                
                # Calculate spectral features
                try:
                    spectrum = np.abs(np.fft.rfft(np.frombuffer(buffer, dtype=np.int16)))
                    if len(spectrum) == 0:
                        self.coordinator.logger.error("FFT produced empty spectrum")
                        return
                        
                    max_val = np.max(spectrum)
                    if max_val == 0:
                        self.coordinator.logger.error("FFT spectrum has zero maximum")
                        return
                        
                    normalized_spectrum = spectrum / max_val
                    
                    if segment.speaker_id not in self._speaker_profiles:
                        self._speaker_profiles[segment.speaker_id] = normalized_spectrum
                    else:
                        # Update existing profile (running average)
                        existing = self._speaker_profiles[segment.speaker_id]
                        if len(existing) != len(normalized_spectrum):
                            self.coordinator.logger.error("Spectrum length mismatch")
                            return
                            
                        self._speaker_profiles[segment.speaker_id] = \
                            0.7 * existing + 0.3 * normalized_spectrum
                except Exception as e:
                    self.coordinator.logger.error(f"FFT calculation error: {e}")
                    raise
                    
            finally:
                # Release buffer
                self.coordinator.release_resource('speaker_isolation', 'buffer', buffer)
                
        except Exception as e:
            self.coordinator.logger.error(f"Speaker profile update error: {e}")
            self.coordinator.handle_error(e, "speaker_isolation")
            
    def process_audio_chunk(self, audio_chunk: bytes) -> List[SpeakerSegment]:
        """
        Process an audio chunk to isolate speakers and speech segments.
        
        Args:
            audio_chunk: Raw audio data
            
        Returns:
            List of detected speaker segments
        """
        if not self.coordinator:
            return []
            
        try:
            # Separate channels
            channel_buffers = self.separate_channels(audio_chunk)
            
            # Process each channel
            all_segments = []
            for i, channel_data in enumerate(channel_buffers):
                segments = self.detect_speech_segments(channel_data, i)
                
                # Update speaker profiles
                for segment in segments:
                    self.update_speaker_profile(segment)
                    
                all_segments.extend(segments)
                
                # Release channel buffer
                self.coordinator.release_resource('speaker_isolation', 'buffer', channel_data)
                
            return all_segments
            
        except Exception as e:
            self.coordinator.logger.error(f"Audio processing error: {e}")
            self.coordinator.handle_error(e, "speaker_isolation")
            return []
            
    def get_speaker_stats(self) -> Dict[str, Dict]:
        """Get statistics about detected speakers."""
        stats = {}
        for speaker_id in self._speaker_profiles:
            stats[speaker_id] = {
                'profile_strength': float(np.mean(self._speaker_profiles[speaker_id])),
                'channel': int(speaker_id.split('_')[1])
            }
            
        if self.coordinator:
            self.coordinator.update_performance_stats('speaker_isolation', {
                'num_speakers': len(stats),
                'profile_strengths': [s['profile_strength'] for s in stats.values()]
            })
            
        return stats
        
    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Clear speaker profiles
            self._speaker_profiles.clear()
            self._current_segment = None
            
            # Unregister from coordinator
            if self.coordinator:
                try:
                    self.coordinator.mark_component_cleanup_complete('speaker_isolation')
                    self.coordinator.unregister_thread()
                except Exception as e:
                    self.coordinator.logger.error(f"Coordinator cleanup error: {e}")
                    self.coordinator.handle_error(e, "speaker_isolation")
                    
        except Exception as e:
            if self.coordinator:
                self.coordinator.logger.error(f"Cleanup error: {e}")
                self.coordinator.handle_error(e, "speaker_isolation")
            raise  # Re-raise to ensure proper error propagation
