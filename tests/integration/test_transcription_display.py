"""
Integration tests for real-time transcription display functionality.
Tests end-to-end transcription visualization, speaker tracking, and performance.
"""

import time
import pytest
from unittest.mock import Mock, patch
from audio_transcriber.transcription_formatter import TranscriptionFormatter
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import IntegrationTest

class TestTranscriptionDisplay(IntegrationTest):
    """Test real-time transcription display and integration."""
    
    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.coordinator = MonitoringCoordinator()
        self.formatter = TranscriptionFormatter(self.coordinator)
        
    @pytest.mark.integration
    def test_realtime_transcription_flow(self):
        """Test end-to-end transcription display flow."""
        # Register test speakers
        self.formatter.register_speaker(0, "Agent")
        self.formatter.register_speaker(1, "Customer")
        
        # Simulate transcription flow with timing
        transcriptions = [
            (0, "Hello, how can I assist you today?", 0.95),
            (1, "Hi, I'm having trouble with my device.", 0.92),
            (0, "I understand. Could you describe the issue?", 0.94),
            (1, "It's not turning on properly.", 0.93)
        ]
        
        display_latency = []
        with patch('builtins.print') as mock_print:
            for channel, text, confidence in transcriptions:
                start_time = time.time()
                self.formatter.add_transcription(channel, text, confidence)
                latency = time.time() - start_time
                display_latency.append(latency)
                
                # Verify immediate display
                self.assertEqual(mock_print.call_count, len(display_latency))
                
        # Verify performance targets
        avg_latency = sum(display_latency) / len(display_latency)
        self.assertLess(avg_latency, 0.1)  # Display latency under 100ms
        
        # Log performance metrics
        self.log_metric("avg_display_latency", avg_latency)
        self.log_metric("max_display_latency", max(display_latency))
        
    @pytest.mark.integration
    def test_speaker_tracking_integration(self):
        """Test speaker tracking and metadata integration."""
        # Register multiple speakers
        speakers = {
            0: "Agent",
            1: "Customer",
            2: "Supervisor"
        }
        for channel, name in speakers.items():
            self.formatter.register_speaker(channel, name)
            
        # Add transcriptions for each speaker
        for channel in speakers:
            self.formatter.add_transcription(
                channel,
                f"Test message from channel {channel}",
                0.9
            )
            
        # Verify speaker stats integration
        stats = self.formatter.get_speaker_stats()
        self.assertEqual(len(stats), len(speakers))
        for speaker in speakers.values():
            self.assertIn(speaker, stats)
            self.assertEqual(stats[speaker]["segment_count"], 1)
            
        # Log metrics
        self.log_metric("total_speakers", len(stats))
        self.log_metric("total_segments", sum(s["segment_count"] for s in stats.values()))
        
    @pytest.mark.integration
    @pytest.mark.slow
    def test_long_session_stability(self):
        """Test stability during long transcription sessions."""
        session_duration = 5  # 5 seconds for test, increase for thorough testing
        interval = 0.1  # Add transcription every 100ms
        start_time = time.time()
        
        message_count = 0
        memory_samples = []
        
        while time.time() - start_time < session_duration:
            # Alternate between channels
            channel = message_count % 2
            self.formatter.add_transcription(
                channel,
                f"Test message {message_count}",
                0.9
            )
            
            # Get recent history to verify memory usage
            recent = self.formatter.get_recent_segments(30.0)
            memory_samples.append(len(recent))
            
            message_count += 1
            time.sleep(interval)
            
        # Verify performance
        self.assertGreater(message_count, 0)
        self.assertLess(max(memory_samples), 1000)  # Memory usage limit
        
        # Get final stats
        stats = self.formatter.get_speaker_stats()
        
        # Log metrics
        self.log_metric("total_messages", message_count)
        self.log_metric("max_recent_segments", max(memory_samples))
        self.log_metric("avg_recent_segments", sum(memory_samples) / len(memory_samples))
        
    @pytest.mark.integration
    def test_coordinator_integration(self):
        """Test integration with monitoring coordinator."""
        # Add test transcriptions
        test_messages = [
            (0, "Test message 1", 0.95),
            (1, "Test message 2", 0.92),
            (0, "Test message 3", 0.94)
        ]
        
        coordinator_updates = []
        def track_update(**kwargs):
            coordinator_updates.append(kwargs)
        
        self.coordinator.update_state = track_update
        
        for channel, text, confidence in test_messages:
            self.formatter.add_transcription(channel, text, confidence)
            
        # Verify coordinator updates
        self.assertEqual(len(coordinator_updates), len(test_messages))
        for update in coordinator_updates:
            self.assertIn("last_transcription", update)
            self.assertIn("transcription_confidence", update)
            
        # Log metrics
        self.log_metric("coordinator_updates", len(coordinator_updates))
        self.log_metric("avg_confidence", 
            sum(u["transcription_confidence"] for u in coordinator_updates) / len(coordinator_updates)
        )
