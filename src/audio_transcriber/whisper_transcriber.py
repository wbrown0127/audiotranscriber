"""
COMPONENT_NOTES:
{
    "name": "WhisperTranscriber",
    "type": "Core Component",
    "description": "Audio transcription system that uses OpenAI's Whisper API with voice activity detection, speaker isolation, and rate limiting",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                WT[WhisperTranscriber] --> WA[WhisperAPI]
                WT --> VAD[VoiceActivityDetector]
                WT --> SI[SpeakerIsolation]
                WT --> RL[RateLimiter]
                WT --> MC[MonitoringCoordinator]
                WA --> TR[TranscriptionResult]
                WA --> TC[TranscriptionCost]
                VAD --> AD[AudioDetection]
                SI --> SP[SpeakerProfile]
                SI --> SH[SpeakerHistory]
                RL --> RQ[RequestQueue]
                RL --> RT[RequestTiming]
                MC --> PS[PerformanceStats]
        ```",
        "dependencies": {
            "WhisperAPI": "OpenAI transcription",
            "VoiceActivityDetector": "Speech detection",
            "SpeakerIsolation": "Speaker tracking",
            "RateLimiter": "API rate control",
            "MonitoringCoordinator": "System monitoring",
            "TranscriptionResult": "Result structure",
            "TranscriptionCost": "Cost tracking",
            "AudioDetection": "Speech analysis",
            "SpeakerProfile": "Speaker data",
            "SpeakerHistory": "History tracking",
            "RequestQueue": "Request management",
            "RequestTiming": "Timing control",
            "PerformanceStats": "Performance tracking"
        }
    },
    "notes": [
        "Handles Whisper API integration",
        "Implements voice activity detection",
        "Manages speaker isolation",
        "Controls API rate limiting",
        "Tracks transcription costs",
        "Maintains speaker histories"
    ],
    "usage": {
        "examples": [
            "transcriber = WhisperTranscriber(api_key, coordinator)",
            "results = await transcriber.transcribe_audio_chunk(audio_data)",
            "history = transcriber.get_speaker_history('speaker_1')",
            "await transcriber.cleanup()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "openai",
            "webrtcvad",
            "asyncio"
        ],
        "system": {
            "api": "OpenAI API access",
            "memory": "Audio buffer capacity"
        }
    },
    "performance": {
        "execution_time": "Real-time transcription",
        "resource_usage": [
            "Rate-limited API calls",
            "Efficient VAD processing",
            "Optimized speaker tracking",
            "Minimal memory footprint"
        ]
    }
}
"""

import logging
import time
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
import webrtcvad
import openai
from .monitoring_coordinator import MonitoringCoordinator
from .speaker_isolation import SpeakerIsolation, SpeakerSegment

logger = logging.getLogger(__name__)

@dataclass
class TranscriptionResult:
    """Represents a single transcription result."""
    text: str
    confidence: float
    speaker_id: str
    timestamp: float
    cost: float
    channel: int
    segment_duration: float

@dataclass
class SpeakerHistory:
    """Tracks transcription history for a specific speaker."""
    speaker_id: str
    channel: int
    transcriptions: List[TranscriptionResult] = None
    total_duration: float = 0.0
    total_cost: float = 0.0
    
    def __post_init__(self):
        if self.transcriptions is None:
            self.transcriptions = []

class WhisperTranscriber:
    """Handles audio transcription using OpenAI's Whisper API."""
    
    def __init__(self, 
                 api_key: str,
                 coordinator: MonitoringCoordinator,
                 max_retries: int = 3,
                 rate_limit_per_min: int = 50,
                 config: Optional[Dict] = None):
        """
        Initialize transcriber.
        
        Args:
            api_key: OpenAI API key
            coordinator: MonitoringCoordinator instance
            max_retries: Maximum retry attempts for failed API calls
            rate_limit_per_min: Maximum API requests per minute
            config: Optional configuration dictionary
        """
        if not api_key:
            raise ValueError("OpenAI API key is required")
        if not coordinator:
            raise ValueError("MonitoringCoordinator is required")
            
        self.client = openai.OpenAI(api_key=api_key)
        self.coordinator = coordinator
        self.max_retries = max_retries
        self.rate_limit = rate_limit_per_min
        self._initialized = False
        
        # Initialize VAD
        self.vad = webrtcvad.Vad(3)  # Aggressiveness level 3
        
        # Initialize speaker isolation with coordinator
        self.speaker_isolation = SpeakerIsolation(coordinator=coordinator)
        self._initialized = True
        
        # Rate limiting
        self.request_times = []
        self.rate_limit_window = 60  # 1 minute window
        
        # Performance tracking
        self._processed_chunks = 0
        self._successful_transcriptions = 0
        self._failed_transcriptions = 0
        self._total_latency = 0.0
        self._total_cost = 0.0
        
        # Speaker tracking
        self._speaker_histories: Dict[str, SpeakerHistory] = {}
        self._consecutive_errors = 0
        
    def _should_process_chunk(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """Check if audio chunk contains speech."""
        try:
            # Use 30ms frames for VAD
            frame_duration = 30  # ms
            frame_size = int(sample_rate * frame_duration / 1000)
            
            # Process frames
            for i in range(0, len(audio_chunk), frame_size):
                frame = audio_chunk[i:i + frame_size]
                if len(frame) == frame_size and self.vad.is_speech(frame, sample_rate):
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"VAD error: {e}")
            return True  # Process audio if VAD fails
            
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        current_time = time.time()
        
        # Remove old requests outside window
        self.request_times = [t for t in self.request_times 
                            if current_time - t < self.rate_limit_window]
                            
        # Check if we're at limit
        if len(self.request_times) >= self.rate_limit:
            return False
            
        # Add current request time
        self.request_times.append(current_time)
        return True
        
    def _update_speaker_history(self, 
                              result: TranscriptionResult,
                              speaker_id: str,
                              channel: int):
        """Update transcription history for a speaker."""
        if speaker_id not in self._speaker_histories:
            self._speaker_histories[speaker_id] = SpeakerHistory(
                speaker_id=speaker_id,
                channel=channel
            )
            
        history = self._speaker_histories[speaker_id]
        history.transcriptions.append(result)
        history.total_duration += result.segment_duration
        history.total_cost += result.cost
        
    async def transcribe_audio_chunk(self, audio_chunk: bytes) -> List[TranscriptionResult]:
        """
        Transcribe an audio chunk.
        
        Args:
            audio_chunk: Raw audio data
            
        Returns:
            List of TranscriptionResult objects
        """
        if not self._initialized:
            raise RuntimeError("WhisperTranscriber not properly initialized")
        self._processed_chunks += 1
        start_time = time.time()
        
        try:
            # Check for speech
            if not self._should_process_chunk(audio_chunk):
                return []
                
            # Check rate limit
            if not self._check_rate_limit():
                logger.warning("Rate limit exceeded, skipping transcription")
                return []
                
            # Process audio for speaker isolation
            segments = self.speaker_isolation.process_audio_chunk(audio_chunk)
            if not segments:
                return []
                
            results = []
            for segment in segments:
                try:
                    # Transcribe segment
                    response = await self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=("audio.wav", segment.audio_data, "audio/wav"),
                        response_format="verbose_json"
                    )
                    
                    # Record request time for rate limiting
                    self.request_times.append(time.time())
                    
                    # Create result
                    result = TranscriptionResult(
                        text=response.text,
                        confidence=response.segments[0].confidence,
                        speaker_id=segment.speaker_id,
                        timestamp=time.time(),
                        cost=0.001,  # Cost per request
                        channel=segment.channel,
                        segment_duration=segment.end_time - segment.start_time
                    )
                    
                    # Update stats
                    self._successful_transcriptions += 1
                    self._total_cost += result.cost
                    
                    # Update speaker history and profile
                    self._update_speaker_history(
                        result,
                        segment.speaker_id,
                        segment.channel
                    )
                    self.speaker_isolation.update_speaker_profile(segment)
                    
                    results.append(result)
                    self._consecutive_errors = 0
                    
                except Exception as e:
                    logger.error(f"API error: {e}")
                    self._failed_transcriptions += 1
                    self._consecutive_errors += 1
                    
                    if self._consecutive_errors >= 3:
                        self.coordinator.handle_error(e, "transcriber")
                        self._consecutive_errors = 0
                        
            # Update latency
            self._total_latency += time.time() - start_time
            return results
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            self._failed_transcriptions += 1
            return []
            
    def get_performance_stats(self) -> Dict:
        """Get transcription performance statistics."""
        total_transcriptions = self._successful_transcriptions + self._failed_transcriptions
        return {
            'processed_chunks': self._processed_chunks,
            'successful_transcriptions': self._successful_transcriptions,
            'failed_transcriptions': self._failed_transcriptions,
            'success_rate': self._successful_transcriptions / max(total_transcriptions, 1),
            'average_latency': self._total_latency / max(total_transcriptions, 1),
            'total_cost': self._total_cost,
            'speakers_detected': len(self._speaker_histories),
            'total_speaker_segments': sum(
                len(h.transcriptions) for h in self._speaker_histories.values()
            ),
            'speaker_profiles': len(self.speaker_isolation._speaker_profiles),
            'speaker_histories': len(self._speaker_histories)
        }
        
    def get_speaker_history(self, speaker_id: str) -> Optional[SpeakerHistory]:
        """Get transcription history for a specific speaker."""
        return self._speaker_histories.get(speaker_id)
        
    def get_all_speaker_histories(self) -> Dict[str, SpeakerHistory]:
        """Get transcription histories for all speakers."""
        return self._speaker_histories.copy()
        
    async def cleanup(self):
        """Clean up resources."""
        try:
            # Clean up speaker isolation
            if hasattr(self, 'speaker_isolation'):
                await self.speaker_isolation.cleanup()
            
            # Clear histories and stats
            self._speaker_histories.clear()
            self._processed_chunks = 0
            self._successful_transcriptions = 0
            self._failed_transcriptions = 0
            self._total_latency = 0.0
            self._total_cost = 0.0
            self._consecutive_errors = 0
            self.request_times.clear()
            
            # Mark as uninitialized
            self._initialized = False
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "transcriber")
