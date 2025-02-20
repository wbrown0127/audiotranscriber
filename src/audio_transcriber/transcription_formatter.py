"""
COMPONENT_NOTES:
{
    "name": "TranscriptionFormatter",
    "type": "Core Component",
    "description": "Real-time transcription formatter that manages multi-channel audio transcription display with speaker tracking and confidence filtering",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TF[TranscriptionFormatter] --> TS[TranscriptionSegment]
                TF --> ST[SpeakerTracker]
                TF --> TH[TranscriptionHistory]
                TF --> MC[MonitoringCoordinator]
                TS --> TM[TimestampManager]
                TS --> CF[ConfidenceFilter]
                ST --> CM[ChannelMapping]
                ST --> SS[SpeakerStats]
                TH --> RH[RecentHistory]
                TH --> FH[FormattedHistory]
                MC --> PS[PerformanceStats]
        ```",
        "dependencies": {
            "TranscriptionSegment": "Segment data structure",
            "SpeakerTracker": "Speaker management",
            "TranscriptionHistory": "History tracking",
            "MonitoringCoordinator": "System monitoring",
            "TimestampManager": "Time tracking",
            "ConfidenceFilter": "Quality control",
            "ChannelMapping": "Speaker mapping",
            "SpeakerStats": "Statistics tracking",
            "RecentHistory": "Recent segments",
            "FormattedHistory": "Display formatting",
            "PerformanceStats": "Performance tracking"
        }
    },
    "notes": [
        "Manages real-time transcription display",
        "Tracks speaker-channel mapping",
        "Filters by confidence threshold",
        "Maintains transcription history",
        "Provides formatted output",
        "Generates speaker statistics"
    ],
    "usage": {
        "examples": [
            "formatter = TranscriptionFormatter(coordinator)",
            "formatter.register_speaker(0, 'John')",
            "formatter.add_transcription(0, 'Hello world', 0.95)",
            "history = formatter.get_formatted_history()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "dataclasses",
            "logging",
            "datetime"
        ],
        "system": {
            "memory": "History buffer capacity",
            "display": "Real-time output capability"
        }
    },
    "performance": {
        "execution_time": "Real-time formatting",
        "resource_usage": [
            "Efficient string formatting",
            "Optimized history tracking",
            "Minimal memory footprint",
            "Fast segment filtering"
        ]
    }
}
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import timedelta

@dataclass
class TranscriptionSegment:
    """Represents a single transcription segment."""
    speaker: str
    channel: int
    timestamp: float  # Timestamp in seconds from start
    text: str
    confidence: float

class TranscriptionFormatter:
    """Handles formatting and display of real-time transcriptions."""
    
    def __init__(self, coordinator=None):
        self.logger = logging.getLogger("TranscriptionFormatter")
        self.coordinator = coordinator
        self.start_time = time.time()
        self.segments: List[TranscriptionSegment] = []
        self.speaker_channels: Dict[int, str] = {}  # Maps channels to speaker names
        self.min_confidence = 0.7  # Minimum confidence threshold for display
        
    def register_speaker(self, channel: int, speaker_name: str) -> None:
        """Register a speaker name for a channel."""
        self.speaker_channels[channel] = speaker_name
        
    def format_timestamp(self, timestamp: float) -> str:
        """Format timestamp as HH:MM:SS."""
        td = timedelta(seconds=int(timestamp))
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        seconds = td.seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
    def add_transcription(self, channel: int, text: str, confidence: float) -> None:
        """Add a new transcription segment."""
        try:
            # Get current timestamp relative to start
            current_time = time.time() - self.start_time
            
            # Get speaker name for channel
            speaker = self.speaker_channels.get(channel, f"Speaker {channel + 1}")
            
            # Create new segment
            segment = TranscriptionSegment(
                speaker=speaker,
                channel=channel,
                timestamp=current_time,
                text=text,
                confidence=confidence
            )
            
            # Only add if confidence meets threshold
            if confidence >= self.min_confidence:
                self.segments.append(segment)
                
                # Format and display the segment
                formatted = self.format_segment(segment)
                print(formatted, flush=True)  # Ensure immediate display
                
                # Update coordinator state if available
                if self.coordinator:
                    self.coordinator.update_state(
                        last_transcription=formatted,
                        transcription_confidence=confidence
                    )
                    
        except Exception as e:
            self.logger.error(f"Error adding transcription: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "transcription_formatter")
                
    def format_segment(self, segment: TranscriptionSegment) -> str:
        """Format a transcription segment for display."""
        return (
            f"{{{segment.speaker} - Channel {segment.channel} - "
            f"{self.format_timestamp(segment.timestamp)} "
            f"\"{segment.text}\"}}"
        )
        
    def get_recent_segments(self, seconds: float = 30.0) -> List[TranscriptionSegment]:
        """Get transcription segments from the last N seconds."""
        if not self.segments:
            return []
            
        current_time = time.time() - self.start_time
        cutoff_time = current_time - seconds
        
        # Find segments within time window, sorted by timestamp
        recent = sorted(
            [seg for seg in self.segments if seg.timestamp >= cutoff_time],
            key=lambda x: x.timestamp
        )
        
        return recent
        
    def get_formatted_history(self, seconds: float = 30.0) -> str:
        """Get formatted history of recent transcriptions."""
        segments = self.get_recent_segments(seconds)
        return " ".join(self.format_segment(seg) for seg in segments)
        
    def clear_history(self) -> None:
        """Clear transcription history."""
        self.segments.clear()
        self.start_time = time.time()
        
    def get_speaker_stats(self) -> Dict[str, Dict[str, float]]:
        """Get speaking statistics for each speaker."""
        stats = {}
        
        for speaker in set(self.speaker_channels.values()):
            speaker_segments = [
                seg for seg in self.segments
                if seg.speaker == speaker
            ]
            
            if speaker_segments:
                total_confidence = sum(seg.confidence for seg in speaker_segments)
                avg_confidence = total_confidence / len(speaker_segments)
                
                stats[speaker] = {
                    'segment_count': len(speaker_segments),
                    'avg_confidence': avg_confidence,
                    'total_duration': speaker_segments[-1].timestamp - speaker_segments[0].timestamp
                }
                
        return stats
