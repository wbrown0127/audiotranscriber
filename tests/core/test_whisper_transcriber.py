"""
Test Updates [2025-02-19]:
- Converted to pytest-asyncio for Python 3.13.1 compatibility
- Removed direct BufferManager access in favor of MonitoringCoordinator
- Added proper lock ordering documentation
- Added comprehensive error context and validation

COMPONENT_NOTES:
{
    "name": "TestWhisperTranscriber",
    "type": "Test Suite",
    "description": "Core test suite for verifying Whisper transcription functionality, including transcription processing, speaker isolation, and performance monitoring",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TWT[TestWhisperTranscriber] --> WT[WhisperTranscriber]
                TWT --> MC[MonitoringCoordinator]
                TWT --> SI[SpeakerIsolation]
                WT --> OAI[OpenAI]
                WT --> TR[TranscriptionResult]
                WT --> SH[SpeakerHistory]
                SI --> SS[SpeakerSegment]
        ```",
        "dependencies": {
            "WhisperTranscriber": "Main component under test",
            "MonitoringCoordinator": "System monitoring and resource management",
            "SpeakerIsolation": "Speaker detection",
            "OpenAI": "Whisper API integration",
            "TranscriptionResult": "Result data structure",
            "SpeakerHistory": "Speaker tracking",
            "SpeakerSegment": "Audio segment data"
        }
    },
    "notes": [
        "Tests transcription with speaker isolation",
        "Verifies speaker history tracking",
        "Tests performance statistics",
        "Validates error handling",
        "Tests API integration",
        "Ensures proper audio processing"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_whisper_transcriber.py",
            "python -m pytest tests/core/test_whisper_transcriber.py -k test_speaker_history"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "pytest-asyncio",
            "openai",
            "numpy",
            "asyncio"
        ],
        "system": {
            "memory": "1GB minimum",
            "api": "OpenAI API key for Whisper"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Moderate CPU usage for audio processing",
            "Network I/O for API calls",
            "Memory for audio buffers"
        ]
    }
}
"""
import pytest
import asyncio
import time
import logging
import numpy as np
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from audio_transcriber.whisper_transcriber import WhisperTranscriber, TranscriptionResult, SpeakerHistory
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.speaker_isolation import SpeakerSegment
import openai
from tests.utilities.base import ComponentTest

# Lock order documentation for reference:
# 1. state_lock: Component state transitions
# 2. metrics_lock: Performance metrics updates
# 3. perf_lock: Performance data collection
# 4. component_lock: Component lifecycle management
# 5. update_lock: Resource updates and allocation

@pytest.mark.asyncio
class TestWhisperTranscriber(ComponentTest):
    async def asyncSetUp(self):
        """Set up test environment."""
        await super().setUp()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            # Initialize coordinator with proper setup and resource management
            self.coordinator = MonitoringCoordinator()
            await self.coordinator.start_monitoring()
            
            # Initialize transcriber with coordinator for resource management
            self.transcriber = WhisperTranscriber(
                api_key="test_key",
                coordinator=self.coordinator,
                max_retries=2,
                rate_limit_per_min=10
            )
            
            # Register component with coordinator
            await self.coordinator.register_component(self.transcriber)
            
            # Initialize speaker isolation with resource management
            await self.transcriber.init_speaker_isolation()
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}", exc_info=True)
            raise
        
    async def asyncTearDown(self):
        """Clean up test environment."""
        try:
            # Follow proper lock ordering during cleanup
            if hasattr(self, 'transcriber'):
                await self.coordinator.unregister_component(self.transcriber)
                await self.transcriber.cleanup()
            
            if hasattr(self, 'coordinator'):
                # Ensure proper resource cleanup
                await self.coordinator.stop_monitoring()
                await self.coordinator.cleanup_resources()
                await self.coordinator.request_shutdown()
                
                # Verify all resources are properly released
                stats = await self.coordinator.get_resource_stats()
                assert stats['active_buffers'] == 0, "Resource leak detected"
                
            # Clean up any mocks
            for attr in dir(self):
                if attr.startswith('mock_'):
                    try:
                        delattr(self, attr)
                    except Exception as e:
                        self.logger.error(f"Error cleaning up mock {attr}: {e}", exc_info=True)
                        
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}", exc_info=True)
            raise
        finally:
            await super().tearDown()
            
    def create_test_audio(self, duration: float, freq: float = 440.0, channel: int = 0) -> bytes:
        """Create test audio data with a sine wave in specified channel."""
        try:
            sample_rate = 16000
            t = np.linspace(0, duration, int(sample_rate * duration))
            audio = np.zeros((int(sample_rate * duration), 2), dtype=np.int16)
            
            # Generate sine wave
            signal = 0.8 * 32767 * np.sin(2 * np.pi * freq * t)  # 80% amplitude
            audio[:, channel] = signal.astype(np.int16)
            
            return audio.tobytes()
            
        except Exception as e:
            self.logger.error(f"Error creating test audio: {e}")
            raise
            
    @pytest.mark.fast
    @patch('openai.OpenAI')
    async def test_transcription_with_speaker_isolation(self, mock_openai_class):
        """Test transcription with speaker isolation and resource management."""
        try:
            # Mock successful transcription
            mock_response = Mock()
            mock_response.text = "Test transcription"
            mock_response.segments = [Mock(confidence=0.95)]
            
            # Create mock client and response
            self.mock_client = MagicMock()
            self.mock_client.audio = MagicMock()
            self.mock_client.audio.transcriptions = MagicMock()
            self.mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
            mock_openai_class.return_value = self.mock_client
            
            # Replace transcriber's client
            self.transcriber.client = self.mock_client
            
            # Create test audio with two channels
            duration = 1.0  # 1 second
            sample_rate = 16000
            t = np.linspace(0, duration, int(sample_rate * duration))
            
            # Create different frequencies for each channel
            left_channel = np.sin(2 * np.pi * 440 * t)  # 440 Hz
            right_channel = np.sin(2 * np.pi * 880 * t)  # 880 Hz
            
            # Combine channels
            stereo_audio = np.vstack((left_channel, right_channel)).T
            test_audio = (stereo_audio * 32767).astype(np.int16).tobytes()
            
            # Allocate buffers for processing
            buffer = await self.coordinator.allocate_buffer('medium')
            
            try:
                # Process audio with real speaker isolation
                segments = await self.transcriber.speaker_isolation.process_audio_chunk(test_audio, buffer)
                self.assertGreater(len(segments), 0, "No speaker segments detected")
                
                # Verify segment structure
                for segment in segments:
                    self.assertIsInstance(segment, SpeakerSegment)
                    self.assertIsNotNone(segment.speaker_id)
                    self.assertIsNotNone(segment.channel)
                    self.assertGreaterEqual(segment.start_time, 0)
                    self.assertGreater(segment.end_time, segment.start_time)
                    self.assertGreater(segment.confidence, 0)
                
                # Process audio with transcription
                results = await self.transcriber.transcribe_audio_chunk(test_audio, buffer)
                
                # Should have results for both channels
                self.assertGreater(len(results), 0)
                
                for result in results:
                    self.assertIsInstance(result, TranscriptionResult)
                    self.assertEqual(result.text, "Test transcription")
                    self.assertEqual(result.confidence, 0.95)
                    self.assertIsNotNone(result.speaker_id)
                    self.assertIsNotNone(result.channel)
                    self.assertGreater(result.timestamp, 0)
                    self.assertGreater(result.cost, 0)
                    self.assertGreater(result.segment_duration, 0)
                    
                # Verify resource state
                stats = await self.coordinator.get_resource_stats()
                self.assertEqual(stats['active_transcriptions'], 0)
                self.assertEqual(stats['active_buffers'], 1)  # Our allocated buffer
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"Transcription with speaker isolation failed: {e}", exc_info=True)
            raise
        finally:
            # Cleanup to ensure test isolation
            if hasattr(self, 'mock_client'):
                del self.mock_client
                
    @pytest.mark.fast
    @patch('openai.OpenAI')
    async def test_speaker_history(self, mock_openai_class):
        """Test speaker history tracking and analysis with resource management."""
        try:
            # Mock successful transcription
            mock_response = Mock()
            mock_response.text = "Test transcription"
            mock_response.segments = [Mock(confidence=0.95)]
            
            # Create mock client and response
            self.mock_client = MagicMock()
            self.mock_client.audio = MagicMock()
            self.mock_client.audio.transcriptions = MagicMock()
            self.mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
            mock_openai_class.return_value = self.mock_client
            
            # Replace transcriber's client
            self.transcriber.client = self.mock_client
            
            # Create test audio for two speakers
            duration = 1.0
            sample_rate = 16000
            t = np.linspace(0, duration, int(sample_rate * duration))
            
            # Different frequencies for different speakers
            speaker1_audio = np.sin(2 * np.pi * 440 * t)  # Speaker 1: 440 Hz
            speaker2_audio = np.sin(2 * np.pi * 880 * t)  # Speaker 2: 880 Hz
            
            # Create stereo audio
            stereo_audio = np.vstack((speaker1_audio, speaker2_audio)).T
            test_audio = (stereo_audio * 32767).astype(np.int16).tobytes()
            
            # Allocate buffers for processing
            buffer = await self.coordinator.allocate_buffer('medium')
            
            try:
                # Process audio with real speaker isolation
                segments = await self.transcriber.speaker_isolation.process_audio_chunk(test_audio, buffer)
                self.assertGreater(len(segments), 0, "No speaker segments detected")
                
                # Process multiple chunks
                for _ in range(3):
                    results = await self.transcriber.transcribe_audio_chunk(test_audio, buffer)
                    
                    # Verify resource state after each chunk
                    stats = await self.coordinator.get_resource_stats()
                    self.assertEqual(stats['active_transcriptions'], 0)
                    self.assertEqual(stats['active_buffers'], 1)  # Our allocated buffer
                
                # Check speaker histories
                histories = await self.transcriber.get_all_speaker_histories()
                self.assertGreater(len(histories), 0)
                
                for speaker_id, history in histories.items():
                    self.assertIsInstance(history, SpeakerHistory)
                    self.assertEqual(history.speaker_id, speaker_id)
                    self.assertGreater(len(history.transcriptions), 0)
                    self.assertGreater(history.total_duration, 0)
                    self.assertGreater(history.total_cost, 0)
                    
                # Test individual speaker history
                first_speaker = next(iter(histories.keys()))
                speaker_history = await self.transcriber.get_speaker_history(first_speaker)
                self.assertIsNotNone(speaker_history)
                self.assertEqual(speaker_history.speaker_id, first_speaker)
                
                # Verify final resource state
                final_stats = await self.coordinator.get_resource_stats()
                self.assertEqual(final_stats['active_transcriptions'], 0)
                self.assertEqual(final_stats['active_buffers'], 1)  # Our allocated buffer
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"Speaker history test failed: {e}", exc_info=True)
            raise
        finally:
            # Cleanup to ensure test isolation
            if hasattr(self, 'mock_client'):
                del self.mock_client
                
    @pytest.mark.fast
    @patch('openai.OpenAI')
    async def test_performance_stats_with_speakers(self, mock_openai_class):
        """Test performance statistics with speaker tracking and resource management."""
        try:
            # Mock successful transcription
            mock_response = Mock()
            mock_response.text = "Test"
            mock_response.segments = [Mock(confidence=0.9)]
            
            # Create mock client and response
            self.mock_client = MagicMock()
            self.mock_client.audio = MagicMock()
            self.mock_client.audio.transcriptions = MagicMock()
            self.mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
            mock_openai_class.return_value = self.mock_client
            
            # Replace transcriber's client
            self.transcriber.client = self.mock_client
            
            # Create stereo test audio
            duration = 1.0
            sample_rate = 16000
            t = np.linspace(0, duration, int(sample_rate * duration))
            stereo_audio = np.vstack((
                np.sin(2 * np.pi * 440 * t),  # Left channel
                np.sin(2 * np.pi * 880 * t)   # Right channel
            )).T
            test_audio = (stereo_audio * 32767).astype(np.int16).tobytes()
            
            # Allocate buffers for processing
            buffer = await self.coordinator.allocate_buffer('medium')
            
            try:
                # Process audio with real speaker isolation
                segments = await self.transcriber.speaker_isolation.process_audio_chunk(test_audio, buffer)
                self.assertGreater(len(segments), 0, "No speaker segments detected")
                
                # Process multiple chunks
                for i in range(3):
                    results = await self.transcriber.transcribe_audio_chunk(test_audio, buffer)
                    
                    # Verify resource state after each chunk
                    stats = await self.coordinator.get_resource_stats()
                    self.assertEqual(stats['active_transcriptions'], 0)
                    self.assertEqual(stats['active_buffers'], 1)  # Our allocated buffer
                    
                    # Verify performance stats incrementally
                    perf_stats = await self.transcriber.get_performance_stats()
                    self.assertEqual(perf_stats['processed_chunks'], i + 1)
                    self.assertEqual(perf_stats['successful_transcriptions'], i + 1)
                    self.assertEqual(perf_stats['failed_transcriptions'], 0)
                
                # Get final stats
                stats = await self.transcriber.get_performance_stats()
                
                # Check basic stats
                self.assertEqual(stats['processed_chunks'], 3)
                self.assertEqual(stats['successful_transcriptions'], 3)
                self.assertEqual(stats['failed_transcriptions'], 0)
                self.assertEqual(stats['success_rate'], 1.0)
                self.assertGreater(stats['average_latency'], 0)
                self.assertGreater(stats['total_cost'], 0)
                
                # Check speaker-related stats
                self.assertGreater(stats['speakers_detected'], 0)
                self.assertGreater(stats['total_speaker_segments'], 0)
                self.assertGreater(stats['speaker_profiles'], 0)
                self.assertGreater(stats['speaker_histories'], 0)
                
                # Verify final resource state
                final_stats = await self.coordinator.get_resource_stats()
                self.assertEqual(final_stats['active_transcriptions'], 0)
                self.assertEqual(final_stats['active_buffers'], 1)  # Our allocated buffer
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"Performance stats test failed: {e}", exc_info=True)
            raise
        finally:
            # Cleanup to ensure test isolation
            if hasattr(self, 'mock_client'):
                del self.mock_client
                
    @pytest.mark.fast
    async def test_error_handling(self):
        """Test error handling and monitoring with resource management."""
        try:
            # Test consecutive errors trigger monitoring
            error_count = 0
            def mock_handle_error(error, component):
                nonlocal error_count
                error_count += 1
                
            self.coordinator.handle_error = mock_handle_error
            
            # Create mock request for APIError
            mock_request = Mock()
            mock_request.method = "POST"
            mock_request.url = "https://api.openai.com/v1/audio/transcriptions"
            mock_request.headers = {}
            mock_request.body = b""
            
            # Create mock error response
            mock_error = {
                "error": {
                    "message": "Test error",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "test_error"
                }
            }
            
            # Create real test audio
            duration = 1.0
            sample_rate = 16000
            t = np.linspace(0, duration, int(sample_rate * duration))
            audio_data = np.sin(2 * np.pi * 440 * t)  # 440 Hz tone
            test_audio = (audio_data * 32767).astype(np.int16).tobytes()
            
            # Create mock client with error
            self.mock_client = MagicMock()
            self.mock_client.audio = MagicMock()
            self.mock_client.audio.transcriptions = MagicMock()
            self.mock_client.audio.transcriptions.create = AsyncMock(
                side_effect=openai.APIError("Test error", request=mock_request, body=mock_error)
            )
            
            # Replace transcriber's client
            self.transcriber.client = self.mock_client
            
            # Allocate buffer for error testing
            buffer = await self.coordinator.allocate_buffer('medium')
            
            try:
                # Process multiple chunks with errors using real audio processing
                for i in range(3):
                    await self.transcriber.transcribe_audio_chunk(test_audio, buffer)
                    
                    # Verify resource state after each error
                    stats = await self.coordinator.get_resource_stats()
                    self.assertEqual(stats['active_transcriptions'], 0)
                    self.assertEqual(stats['active_buffers'], 1)  # Our allocated buffer
                    
                    # Verify error stats incrementally
                    error_stats = await self.coordinator.get_error_stats()
                    self.assertEqual(error_stats['error_count'], i + 1)
                    self.assertIn('api_error', error_stats['error_types'])
                    
                # Verify error handling
                self.assertEqual(error_count, 1)  # Should trigger after 3 consecutive errors
                stats = await self.transcriber.get_performance_stats()
                self.assertEqual(stats['failed_transcriptions'], 3)
                self.assertEqual(stats['success_rate'], 0.0)
                
                # Verify error tracking
                self.assertTrue(await self.coordinator.has_errors())
                error_info = await self.coordinator.get_last_error()
                self.assertIsNotNone(error_info)
                self.assertEqual(error_info['type'], 'APIError')
                
                # Verify final resource state
                final_stats = await self.coordinator.get_resource_stats()
                self.assertEqual(final_stats['active_transcriptions'], 0)
                self.assertEqual(final_stats['active_buffers'], 1)  # Our allocated buffer
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"Error handling test failed: {e}", exc_info=True)
            raise
        finally:
            # Cleanup to ensure test isolation
            if hasattr(self, 'mock_client'):
                del self.mock_client

if __name__ == '__main__':
    unittest.main()
