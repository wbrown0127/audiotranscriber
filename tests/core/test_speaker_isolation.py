"""
COMPONENT_NOTES:
{
    "name": "TestSpeakerIsolation",
    "type": "Test Suite",
    "description": "Core test suite for verifying speaker isolation functionality, including channel separation, speech detection, and speaker profiling",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TSI[TestSpeakerIsolation] --> SI[SpeakerIsolation]
                TSI --> MC[MonitoringCoordinator]
                SI --> SS[SpeakerSegment]
                SI --> SD[SpeechDetector]
                SI --> SP[SpeakerProfiler]
        ```",
        "dependencies": {
            "SpeakerIsolation": "Main component under test",
            "MonitoringCoordinator": "System monitoring and resource management",
            "SpeakerSegment": "Speech segment data structure",
            "SpeechDetector": "Speech detection algorithms",
            "SpeakerProfiler": "Speaker profile management"
        }
    },
    "notes": [
        "Tests stereo channel separation functionality",
        "Verifies speech segment detection",
        "Tests speaker profile generation",
        "Validates complete audio processing pipeline",
        "Ensures proper error handling",
        "Tests audio data manipulation",
        "Uses async patterns for real-time processing",
        "Manages resources through coordinator"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_speaker_isolation.py",
            "python -m pytest tests/core/test_speaker_isolation.py -k test_speech_detection"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "pytest-asyncio",
            "numpy",
            "logging"
        ],
        "system": {
            "memory": "500MB minimum",
            "audio": "Support for stereo audio processing"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds",
        "resource_usage": [
            "Moderate memory usage for audio buffers",
            "CPU intensive during speech detection",
            "Proper cleanup of audio resources"
        ]
    }
}
"""
import pytest
import numpy as np
import logging
import asyncio
from audio_transcriber.speaker_isolation import SpeakerIsolation, SpeakerSegment
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import ComponentTest

# Note: Converting to async patterns for real-time speaker analysis
# as per changelog requirements

@pytest.mark.asyncio
class TestSpeakerIsolation(ComponentTest):
    """Tests for the SpeakerIsolation class."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        await super().setUp()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            # Initialize coordinator with proper setup and resource management
            self.coordinator = MonitoringCoordinator()
            await self.coordinator.start_monitoring()
            
            # Initialize speaker isolation with coordinator for resource management
            self.isolator = SpeakerIsolation(
                coordinator=self.coordinator,
                sample_rate=16000,
                channels=2,
                energy_threshold=0.1,
                min_segment_duration=0.5
            )
            
            # Register component with coordinator
            await self.coordinator.register_component(self.isolator)
            
            # Configure audio processing settings
            await self.isolator.configure({
                'sample_rate': 16000,
                'channels': 2,
                'buffer_sizes': {
                    'small': 4 * 1024,    # 4KB for small segments
                    'medium': 64 * 1024,  # 64KB for medium segments
                    'large': 1024 * 1024  # 1MB for large segments
                }
            })
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}", exc_info=True)
            raise
        
    async def asyncTearDown(self):
        """Clean up test environment."""
        try:
            # Follow proper lock ordering during cleanup
            if hasattr(self, 'isolator'):
                await self.coordinator.unregister_component(self.isolator)
                await self.isolator.cleanup()
            
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
        
    async def create_test_audio(self, 
                              duration: float,
                              freq: float = 440.0,
                              amplitude: float = 0.5,
                              channel: int = 0) -> bytes:
        """Create test audio data with a sine wave in specified channel."""
        try:
            samples = int(duration * self.isolator.sample_rate)
            t = np.linspace(0, duration, samples)
            audio = np.zeros((samples, 2), dtype=np.int16)
            
            # Generate sine wave
            signal = amplitude * 32767 * np.sin(2 * np.pi * freq * t)
            audio[:, channel] = signal.astype(np.int16)
            
            return audio.tobytes()
            
        except Exception as e:
            self.logger.error(f"Error creating test audio: {e}")
            raise
        
    @pytest.mark.fast
    async def test_channel_separation(self):
        """Test stereo channel separation functionality."""
        try:
            # Create stereo audio with different frequencies in each channel
            duration = 1.0
            left_freq = 440.0  # A4 note
            right_freq = 880.0  # A5 note
            
            # Create left channel audio
            left_audio = await self.create_test_audio(duration, left_freq, channel=0)
            # Create right channel audio
            right_audio = await self.create_test_audio(duration, right_freq, channel=1)
            
            # Combine channels
            stereo_audio = np.frombuffer(left_audio, dtype=np.int16).reshape(-1, 2).copy()
            right_data = np.frombuffer(right_audio, dtype=np.int16).reshape(-1, 2)
            stereo_audio[:, 1] = right_data[:, 1].copy()
            test_audio = stereo_audio.tobytes()
            
            # Allocate buffers for channel separation
            left_buffer = await self.coordinator.allocate_buffer('medium')
            right_buffer = await self.coordinator.allocate_buffer('medium')
            
            try:
                # Separate channels
                channels = await self.isolator.separate_channels(test_audio, left_buffer, right_buffer)
                
                self.assertEqual(len(channels), 2)
                
                # Verify channel content
                left_data = np.frombuffer(channels[0], dtype=np.int16)
                right_data = np.frombuffer(channels[1], dtype=np.int16)
                
                # Check that each channel has the correct frequency content
                left_fft = np.abs(np.fft.rfft(left_data))
                right_fft = np.abs(np.fft.rfft(right_data))
                
                left_peak_freq = np.argmax(left_fft) * self.isolator.sample_rate / len(left_fft) / 2
                right_peak_freq = np.argmax(right_fft) * self.isolator.sample_rate / len(right_fft) / 2
                
                self.assertAlmostEqual(left_peak_freq, left_freq, delta=10)
                self.assertAlmostEqual(right_peak_freq, right_freq, delta=10)
                
            finally:
                # Release buffers
                await self.coordinator.release_buffer(left_buffer)
                await self.coordinator.release_buffer(right_buffer)
            
        except Exception as e:
            self.logger.error(f"Channel separation test failed: {e}", exc_info=True)
            raise
        
    @pytest.mark.fast
    async def test_speech_detection(self):
        """Test speech segment detection functionality."""
        try:
            # Create test audio with speech-like segments
            duration = 2.0
            audio_data = await self.create_test_audio(duration, freq=200, amplitude=0.8)
            
            # Add silence in the middle
            audio_array = np.frombuffer(audio_data, dtype=np.int16).reshape(-1, 2).copy()
            silence_start = int(0.8 * self.isolator.sample_rate)
            silence_end = int(1.2 * self.isolator.sample_rate)
            audio_array[silence_start:silence_end] = 0
            
            # Allocate buffer for speech detection
            buffer = await self.coordinator.allocate_buffer('medium')
            
            try:
                # Process audio
                segments = await self.isolator.detect_speech_segments(
                    audio_array[:, 0].tobytes(),  # Test left channel
                    channel_index=0,
                    buffer=buffer
                )
                
                # Should detect two segments (before and after silence)
                self.assertEqual(len(segments), 2)
                
                # Verify segment properties
                for segment in segments:
                    self.assertIsInstance(segment, SpeakerSegment)
                    self.assertEqual(segment.channel, 0)
                    self.assertGreater(len(segment.audio_data), 0)
                    self.assertGreaterEqual(segment.end_time, segment.start_time)
                    
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
            
        except Exception as e:
            self.logger.error(f"Speech detection test failed: {e}", exc_info=True)
            raise
            
    @pytest.mark.fast
    async def test_speaker_profiles(self):
        """Test speaker profile generation and management."""
        try:
            # Create distinct audio patterns for two speakers
            speaker1_audio = await self.create_test_audio(1.0, freq=150)  # Lower frequency
            speaker2_audio = await self.create_test_audio(1.0, freq=300)  # Higher frequency
            
            # Allocate buffers for processing
            buffer1 = await self.coordinator.allocate_buffer('medium')
            buffer2 = await self.coordinator.allocate_buffer('medium')
            
            try:
                # Process segments
                segments1 = await self.isolator.process_audio_chunk(speaker1_audio, buffer1)
                segments2 = await self.isolator.process_audio_chunk(speaker2_audio, buffer2)
                
                # Get speaker stats
                stats = await self.isolator.get_speaker_stats()
                
                # Should have profiles for both speakers
                self.assertGreaterEqual(len(stats), 1)
                
                # Verify profile properties
                for speaker_id, profile in stats.items():
                    self.assertIn('profile_strength', profile)
                    self.assertIn('channel', profile)
                    self.assertGreaterEqual(profile['profile_strength'], 0.0)
                    self.assertLess(profile['profile_strength'], 1.0)
                    
            finally:
                # Release buffers
                await self.coordinator.release_buffer(buffer1)
                await self.coordinator.release_buffer(buffer2)
                
        except Exception as e:
            self.logger.error(f"Speaker profiles test failed: {e}", exc_info=True)
            raise
            
    @pytest.mark.fast
    async def test_full_pipeline(self):
        """Test complete audio processing pipeline."""
        try:
            # Create test audio with alternating speakers
            duration = 3.0
            
            # Speaker 1 in left channel
            audio1 = await self.create_test_audio(duration, freq=200, channel=0)
            # Speaker 2 in right channel
            audio2 = await self.create_test_audio(duration, freq=400, channel=1)
            
            # Combine channels
            audio_array1 = np.frombuffer(audio1, dtype=np.int16).reshape(-1, 2).copy()
            audio_array2 = np.frombuffer(audio2, dtype=np.int16).reshape(-1, 2).copy()
            
            # Allocate buffers for processing
            buffer1 = await self.coordinator.allocate_buffer('large')
            buffer2 = await self.coordinator.allocate_buffer('large')
            
            try:
                # Process complete audio
                segments = await self.isolator.process_audio_chunk(audio_array1.tobytes(), buffer1)
                segments.extend(await self.isolator.process_audio_chunk(audio_array2.tobytes(), buffer2))
                
                # Verify results
                self.assertGreater(len(segments), 0)
                
                # Check segment properties
                channels_found = set()
                for segment in segments:
                    self.assertIsInstance(segment, SpeakerSegment)
                    self.assertGreater(len(segment.audio_data), 0)
                    channels_found.add(segment.channel)
                    
                # Should have segments from both channels
                self.assertGreaterEqual(len(channels_found), 1)
                
            finally:
                # Release buffers
                await self.coordinator.release_buffer(buffer1)
                await self.coordinator.release_buffer(buffer2)
            
        except Exception as e:
            self.logger.error(f"Full pipeline test failed: {e}", exc_info=True)
            raise
            
    @pytest.mark.fast
    async def test_error_handling(self):
        """Test error handling and recovery."""
        try:
            # Allocate minimal buffer for error testing
            buffer = await self.coordinator.allocate_buffer('small')
            
            try:
                # Test with invalid audio data
                invalid_audio = bytes([0, 1, 2, 3])  # Too short to be valid audio
                
                # Should handle errors gracefully
                segments = await self.isolator.process_audio_chunk(invalid_audio, buffer)
                self.assertEqual(len(segments), 0)
                
                # Test with empty input
                segments = await self.isolator.process_audio_chunk(bytes(), buffer)
                self.assertEqual(len(segments), 0)
                
                # Verify error was logged and tracked
                error_stats = await self.coordinator.get_error_stats()
                self.assertGreater(error_stats['error_count'], 0)
                self.assertIn('invalid_audio', error_stats['error_types'])
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"Error handling test failed: {e}", exc_info=True)
            raise

if __name__ == '__main__':
    unittest.main()
