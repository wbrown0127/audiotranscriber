"""
COMPONENT_NOTES:
{
    "name": "TestTranscriptionFormatter",
    "type": "Test Suite",
    "description": "Core test suite for verifying transcription formatting functionality, including real-time display, formatting, and history management",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TTF[TestTranscriptionFormatter] --> TF[TranscriptionFormatter]
                TTF --> TS[TranscriptionSegment]
                TTF --> CT[ComponentTest]
                TF --> TS
                TF --> SF[SpeakerFormatter]
                TF --> TH[TranscriptionHistory]
                TF --> RT[RealTimeDisplay]
        ```",
        "dependencies": {
            "TranscriptionFormatter": "Main component under test",
            "TranscriptionSegment": "Segment data structure",
            "ComponentTest": "Base test functionality",
            "SpeakerFormatter": "Speaker name formatting",
            "TranscriptionHistory": "History management",
            "RealTimeDisplay": "Live display updates"
        }
    },
    "notes": [
        "Tests speaker registration and channel mapping",
        "Verifies timestamp formatting",
        "Tests transcription segment formatting",
        "Validates confidence filtering",
        "Tests recent history retrieval",
        "Ensures proper real-time display"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_transcription_formatter.py",
            "python -m pytest tests/core/test_transcription_formatter.py -k test_speaker_registration"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "unittest.mock",
            "time"
        ],
        "system": {
            "memory": "100MB minimum",
            "storage": "Space for transcription history"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Light memory usage",
            "Minimal CPU usage",
            "Storage for transcription history"
        ]
    }
}
"""

import time
import pytest
from unittest.mock import Mock, patch
from audio_transcriber.transcription_formatter import TranscriptionFormatter, TranscriptionSegment
from tests.utilities.base import ComponentTest

class TestTranscriptionFormatter(ComponentTest):
    """Test transcription formatting and display functionality."""
    
    def setUp(self):
        """Set up test environment."""
        super().setUp()
        
        # Initialize coordinator
        from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
        self.coordinator = MonitoringCoordinator()
        self.coordinator.start_monitoring()
        
        # Initialize resource pool through coordinator
        self.coordinator.initialize_resource_pool({
            'memory': 1024 * 1024 * 10,  # 10MB for text buffers
            'handles': 50,  # File handles for history
            'buffer': {
                4096: 100,    # Small text buffers
                65536: 50,    # Medium text buffers
            }
        })
        
        # Initialize channels
        for channel in ['left', 'right']:
            self.coordinator.initialize_channel(channel)
        
        # Create formatter with coordinator
        self.formatter = TranscriptionFormatter(coordinator=self.coordinator)
        
    def tearDown(self):
        """Clean up test environment."""
        try:
            # Get initial resource metrics
            initial_metrics = self.coordinator.get_resource_metrics()
            
            # Cleanup formatter
            self.formatter.clear_history()
            
            # Verify resources were released
            final_metrics = self.coordinator.get_resource_metrics()
            assert final_metrics['current_used'] <= initial_metrics['current_used']
            
            # Cleanup coordinator
            if hasattr(self, 'coordinator'):
                # Cleanup channels in reverse order
                for channel in ['right', 'left']:
                    self.coordinator.cleanup_channel(channel)
                self.coordinator.stop_monitoring()
                self.coordinator.cleanup()
        finally:
            super().tearDown()
        
    @pytest.mark.fast
    def test_speaker_registration(self):
        """Test speaker registration and channel mapping."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Register speakers through coordinator
        self.coordinator.register_speaker(0, "Customer")
        self.coordinator.register_speaker(1, "Agent")
        
        # Allocate text buffers through coordinator
        buffer_id1 = self.coordinator.allocate_buffer(len("Hello, I need help."))
        buffer_id2 = self.coordinator.allocate_buffer(len("How can I assist you today?"))
        
        try:
            # Add transcriptions for both channels
            self.formatter.add_transcription(0, "Hello, I need help.", 0.95, buffer_id1)
            self.formatter.add_transcription(1, "How can I assist you today?", 0.92, buffer_id2)
            
            # Verify speaker names in segments
            segments = self.formatter.segments
            self.assertEqual(len(segments), 2)
            self.assertEqual(segments[0].speaker, "Customer")
            self.assertEqual(segments[1].speaker, "Agent")
            
            # Get speaker metrics from coordinator
            speaker_metrics = self.coordinator.get_speaker_metrics()
            
            # Log metrics
            self.log_metric("registered_speakers", speaker_metrics['registered_count'])
            self.log_metric("active_speakers", speaker_metrics['active_count'])
            self.log_metric("speaker_buffer_usage", speaker_metrics['buffer_usage'])
            
        finally:
            # Release buffers
            self.coordinator.release_buffer(buffer_id1)
            self.coordinator.release_buffer(buffer_id2)
            
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
        
    @pytest.mark.fast
    def test_timestamp_formatting(self):
        """Test timestamp formatting."""
        # Test various durations
        test_times = [
            (45, "00:00:45"),      # 45 seconds
            (90, "00:01:30"),      # 1 minute 30 seconds
            (3665, "01:01:05"),    # 1 hour 1 minute 5 seconds
        ]
        
        for seconds, expected in test_times:
            formatted = self.formatter.format_timestamp(seconds)
            self.assertEqual(formatted, expected)
            
        # Get performance metrics from coordinator
        perf_metrics = self.coordinator.get_performance_metrics()
        
        # Log metrics
        self.log_metric("timestamp_tests", len(test_times))
        self.log_metric("format_latency", perf_metrics['format_latency'])
        self.log_metric("format_operations", perf_metrics['format_operations'])
        
    @pytest.mark.fast
    def test_segment_formatting(self):
        """Test transcription segment formatting."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Allocate text buffer through coordinator
        text = "How can I help you today?"
        buffer_id = self.coordinator.allocate_buffer(len(text))
        
        try:
            # Create test segment
            segment = TranscriptionSegment(
                speaker="Agent",
                channel=1,
                timestamp=105.5,  # 1 minute 45 seconds
                text=text,
                confidence=0.95,
                buffer_id=buffer_id
            )
            
            # Format segment
            formatted = self.formatter.format_segment(segment)
            expected = "{Agent - Channel 1 - 00:01:45 \"How can I help you today?\"}"
            self.assertEqual(formatted, expected)
            
            # Get format metrics from coordinator
            format_metrics = self.coordinator.get_format_metrics()
            
            # Log metrics
            self.log_metric("format_length", len(formatted))
            self.log_metric("format_time", format_metrics['format_time'])
            self.log_metric("buffer_utilization", format_metrics['buffer_utilization'])
            
        finally:
            # Release buffer
            self.coordinator.release_buffer(buffer_id)
            
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
        
    @pytest.mark.fast
    def test_confidence_filtering(self):
        """Test confidence threshold filtering."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Add transcriptions with varying confidence
        test_cases = [
            ("High confidence", 0.95, True),
            ("Medium confidence", 0.75, True),
            ("Low confidence", 0.65, False),
            ("Very low confidence", 0.30, False)
        ]
        
        buffer_ids = []
        try:
            # Add transcriptions with buffer allocation
            for text, confidence, should_display in test_cases:
                # Allocate buffer through coordinator
                buffer_id = self.coordinator.allocate_buffer(len(text))
                buffer_ids.append(buffer_id)
                
                # Add transcription with buffer
                self.formatter.add_transcription(0, text, confidence, buffer_id)
            
            # Verify only high confidence segments were added
            segments = self.formatter.segments
            self.assertEqual(len(segments), 2)  # Only high and medium confidence
            self.assertTrue(all(seg.confidence >= 0.7 for seg in segments))
            
            # Get confidence metrics from coordinator
            confidence_metrics = self.coordinator.get_confidence_metrics()
            
            # Log metrics
            self.log_metric("total_transcriptions", len(test_cases))
            self.log_metric("displayed_transcriptions", len(segments))
            self.log_metric("avg_confidence", confidence_metrics['average'])
            self.log_metric("min_confidence", confidence_metrics['minimum'])
            self.log_metric("max_confidence", confidence_metrics['maximum'])
            self.log_metric("filtered_count", confidence_metrics['filtered_count'])
            
        finally:
            # Release all buffers
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
                
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
        
    @pytest.mark.fast
    def test_recent_history(self):
        """Test recent history retrieval."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Set up test timestamps
        base_time = time.time()
        self.formatter.start_time = base_time
        
        # Add segments with relative timestamps
        test_segments = [
            (90.0, "Recent message"),      # 90 seconds from start
            (70.0, "Older message"),       # 70 seconds from start
            (40.0, "Old message"),         # 40 seconds from start
            (10.0, "Very old message")     # 10 seconds from start
        ]
        
        buffer_ids = []
        try:
            # Add segments with buffer allocation
            for timestamp, text in test_segments:
                # Allocate buffer through coordinator
                buffer_id = self.coordinator.allocate_buffer(len(text))
                buffer_ids.append(buffer_id)
                
                # Create segment with buffer
                segment = TranscriptionSegment(
                    speaker="Test",
                    channel=0,
                    timestamp=timestamp,
                    text=text,
                    confidence=0.9,
                    buffer_id=buffer_id
                )
                self.formatter.segments.append(segment)
            
            # Get recent segments (last 30 seconds)
            with patch('time.time', return_value=base_time + 100):  # Mock current time to 100s from start
                recent = self.formatter.get_recent_segments(30.0)
                self.assertEqual(len(recent), 2)  # Should get the two most recent messages
                self.assertEqual(recent[0].text, "Older message")
                self.assertEqual(recent[1].text, "Recent message")
            
            # Get history metrics from coordinator
            history_metrics = self.coordinator.get_history_metrics()
            
            # Log metrics
            self.log_metric("total_segments", len(test_segments))
            self.log_metric("recent_segments", len(recent))
            self.log_metric("history_size", history_metrics['total_size'])
            self.log_metric("avg_segment_age", history_metrics['avg_segment_age'])
            self.log_metric("oldest_segment_age", history_metrics['oldest_segment_age'])
            self.log_metric("buffer_utilization", history_metrics['buffer_utilization'])
            
        finally:
            # Release all buffers
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
                
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
        
    @pytest.mark.fast
    def test_speaker_statistics(self):
        """Test speaker statistics calculation."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        # Register speakers through coordinator
        self.coordinator.register_speaker(0, "Customer")
        self.coordinator.register_speaker(1, "Agent")
        
        # Add multiple transcriptions
        transcriptions = [
            (0, "Hello, I need help.", 0.92),
            (1, "How can I assist you?", 0.95),
            (0, "My device isn't working.", 0.88),
            (1, "Let me help you with that.", 0.94)
        ]
        
        buffer_ids = []
        try:
            # Add transcriptions with buffer allocation
            for channel, text, confidence in transcriptions:
                # Allocate buffer through coordinator
                buffer_id = self.coordinator.allocate_buffer(len(text))
                buffer_ids.append(buffer_id)
                
                # Add transcription with buffer
                self.formatter.add_transcription(channel, text, confidence, buffer_id)
            
            # Get speaker stats through coordinator
            speaker_metrics = self.coordinator.get_speaker_metrics()
            
            # Verify stats
            self.assertEqual(speaker_metrics['speaker_count'], 2)
            self.assertEqual(speaker_metrics['speakers']['Customer']['segment_count'], 2)
            self.assertEqual(speaker_metrics['speakers']['Agent']['segment_count'], 2)
            self.assertGreater(speaker_metrics['speakers']['Agent']['avg_confidence'], 0.9)
            
            # Log metrics
            self.log_metric("speaker_count", speaker_metrics['speaker_count'])
            self.log_metric("total_segments", speaker_metrics['total_segments'])
            self.log_metric("avg_confidence", speaker_metrics['avg_confidence'])
            for speaker, stats in speaker_metrics['speakers'].items():
                self.log_metric(f"{speaker}_segments", stats['segment_count'])
                self.log_metric(f"{speaker}_avg_confidence", stats['avg_confidence'])
                self.log_metric(f"{speaker}_buffer_usage", stats['buffer_usage'])
            
        finally:
            # Release all buffers
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
                
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
            
    @pytest.mark.fast
    def test_realtime_display(self):
        """Test real-time transcription display."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        buffer_ids = []
        try:
            with patch('builtins.print') as mock_print:
                # Add transcriptions with minimal delay
                transcriptions = [
                    (0, "Hello", 0.95),
                    (1, "Hi there", 0.92),
                    (0, "How are you?", 0.94)
                ]
                
                for channel, text, confidence in transcriptions:
                    # Allocate buffer through coordinator
                    buffer_id = self.coordinator.allocate_buffer(len(text))
                    buffer_ids.append(buffer_id)
                    
                    # Add transcription with buffer
                    self.formatter.add_transcription(channel, text, confidence, buffer_id)
                    
                # Verify immediate display
                self.assertEqual(mock_print.call_count, 3)
                
                # Get display metrics from coordinator
                display_metrics = self.coordinator.get_display_metrics()
                
                # Verify coordinator updates
                expected_calls = len(transcriptions)
                actual_calls = display_metrics['update_count']
                self.assertEqual(actual_calls, expected_calls)
                
                # Log metrics
                self.log_metric("display_calls", mock_print.call_count)
                self.log_metric("state_updates", actual_calls)
                self.log_metric("display_latency", display_metrics['latency'])
                self.log_metric("refresh_rate", display_metrics['refresh_rate'])
                self.log_metric("buffer_utilization", display_metrics['buffer_utilization'])
                
        finally:
            # Release all buffers
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
                
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
        
    @pytest.mark.fast
    def test_history_management(self):
        """Test history management and cleanup."""
        # Get initial resource metrics
        initial_metrics = self.coordinator.get_resource_metrics()
        
        buffer_ids = []
        try:
            # Add initial transcriptions with buffer allocation
            for i in range(5):
                text = f"Test message {i}"
                buffer_id = self.coordinator.allocate_buffer(len(text))
                buffer_ids.append(buffer_id)
                self.formatter.add_transcription(0, text, 0.9, buffer_id)
            
            # Verify history
            self.assertEqual(len(self.formatter.segments), 5)
            
            # Get history metrics before clear
            pre_clear_metrics = self.coordinator.get_history_metrics()
            self.log_metric("pre_clear_size", pre_clear_metrics['total_size'])
            self.log_metric("pre_clear_segments", len(self.formatter.segments))
            
            # Clear history and release buffers
            self.formatter.clear_history()
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
            buffer_ids.clear()
            
            # Verify cleared
            self.assertEqual(len(self.formatter.segments), 0)
            
            # Add new transcription after clear
            text = "New message"
            buffer_id = self.coordinator.allocate_buffer(len(text))
            buffer_ids.append(buffer_id)
            self.formatter.add_transcription(0, text, 0.9, buffer_id)
            self.assertEqual(len(self.formatter.segments), 1)
            
            # Get final history metrics
            final_history_metrics = self.coordinator.get_history_metrics()
            
            # Log metrics
            self.log_metric("initial_segments", 5)
            self.log_metric("final_segments", 1)
            self.log_metric("total_managed_segments", final_history_metrics['total_managed'])
            self.log_metric("cleared_segments", final_history_metrics['cleared_count'])
            self.log_metric("current_buffer_usage", final_history_metrics['buffer_usage'])
            
        finally:
            # Release any remaining buffers
            for buffer_id in buffer_ids:
                self.coordinator.release_buffer(buffer_id)
                
        # Verify resource cleanup
        final_metrics = self.coordinator.get_resource_metrics()
        self.assertEqual(final_metrics['current_used'], initial_metrics['current_used'])
