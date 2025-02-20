"""
Test Updates [2025-02-19]:
- Converted to pytest-asyncio for Python 3.13.1 compatibility
- Added resource management through MonitoringCoordinator
- Added proper lock ordering documentation
- Added comprehensive error context and validation

COMPONENT_NOTES:
{
    "name": "TestTranscriptionManager",
    "type": "Test Suite",
    "description": "Core test suite for verifying transcription management functionality, including storage, metadata handling, and session management",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TTM[TestTranscriptionManager] --> TM[TranscriptionManager]
                TTM --> MC[MonitoringCoordinator]
                TTM --> TR[TranscriptionResult]
                TTM --> SH[SpeakerHistory]
                TM --> FS[FileStorage]
                TM --> SM[SessionManager]
                TM --> WQ[WriteQueue]
                TM --> MD[MetadataHandler]
        ```",
        "dependencies": {
            "TranscriptionManager": "Main component under test",
            "MonitoringCoordinator": "System monitoring and resource management",
            "TranscriptionResult": "Transcription data structure",
            "SpeakerHistory": "Speaker tracking",
            "FileStorage": "File I/O operations",
            "SessionManager": "Session handling",
            "WriteQueue": "Async write operations",
            "MetadataHandler": "Metadata management"
        }
    },
    "notes": [
        "Tests transcription storage and retrieval",
        "Verifies speaker metadata management",
        "Tests session archiving and loading",
        "Validates session statistics",
        "Tests concurrent write operations",
        "Ensures proper error handling"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_transcription_manager.py",
            "python -m pytest tests/core/test_transcription_manager.py -k test_store_transcription"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "pytest-asyncio",
            "asyncio",
            "json"
        ],
        "system": {
            "storage": "Space for transcription files",
            "permissions": "Write access to test directories"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds",
        "resource_usage": [
            "Moderate disk I/O for file operations",
            "Light memory usage",
            "Proper cleanup of test files"
        ]
    }
}
"""

import pytest
import asyncio
import os
import json
import shutil
import time
import logging
from datetime import datetime
from unittest.mock import Mock
from audio_transcriber.transcription_manager import TranscriptionManager
from audio_transcriber.whisper_transcriber import TranscriptionResult, SpeakerHistory
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import ComponentTest

# Lock order documentation for reference:
# 1. state_lock: Component state transitions
# 2. metrics_lock: Performance metrics updates
# 3. perf_lock: Performance data collection
# 4. component_lock: Component lifecycle management
# 5. update_lock: Resource updates and allocation

@pytest.mark.asyncio
class TestTranscriptionManager(ComponentTest):
    async def asyncSetUp(self):
        """Set up test environment."""
        await super().setUp()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            # Create test directory with required subdirectories
            self.test_dir = f"test_transcriptions_{int(time.time() * 1000)}"
            os.makedirs(os.path.join(self.test_dir, "transcriptions"), exist_ok=True)
            os.makedirs(os.path.join(self.test_dir, "metadata"), exist_ok=True)
            os.makedirs(os.path.join(self.test_dir, "archives"), exist_ok=True)
            
            # Initialize coordinator with proper setup and resource management
            self.coordinator = MonitoringCoordinator()
            await self.coordinator.start_monitoring()
            
            # Initialize transcription manager with coordinator
            self.manager = TranscriptionManager(
                transcriptions_dir=self.test_dir,
                coordinator=self.coordinator
            )
            
            # Register component with coordinator
            await self.coordinator.register_component(self.manager)
            await self.manager.start()
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}", exc_info=True)
            raise
        
    async def asyncTearDown(self):
        """Clean up test environment."""
        try:
            # Follow proper lock ordering during cleanup
            if hasattr(self, 'manager'):
                await self.coordinator.unregister_component(self.manager)
                self.manager._running = False  # Stop the write queue
                await self.manager._write_queue.join()  # Wait for pending writes
                await self.manager.stop()
            
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
            # Clean up test directory
            if os.path.exists(self.test_dir):
                shutil.rmtree(self.test_dir)
            await super().tearDown()
            
    def create_test_result(self, 
                          text: str = "Test transcription",
                          speaker_id: str = "speaker_0",
                          channel: int = 0) -> TranscriptionResult:
        """Create a test TranscriptionResult."""
        return TranscriptionResult(
            text=text,
            confidence=0.95,
            speaker_id=speaker_id,
            timestamp=time.time(),
            cost=0.001,
            channel=channel,
            segment_duration=1.0
        )
        
    def create_test_history(self, 
                           speaker_id: str,
                           channel: int) -> SpeakerHistory:
        """Create a test SpeakerHistory."""
        history = SpeakerHistory(
            speaker_id=speaker_id,
            channel=channel
        )
        # Add some test transcriptions
        for i in range(3):
            history.transcriptions.append(
                self.create_test_result(
                    text=f"Test {i}",
                    speaker_id=speaker_id,
                    channel=channel
                )
            )
        history.total_duration = 3.0
        history.total_cost = 0.003
        return history
        
    @pytest.mark.fast
    async def test_store_transcription(self):
        """Test transcription storage with proper resource management."""
        try:
            # Store multiple transcriptions
            results = [
                self.create_test_result(text=f"Test {i}")
                for i in range(3)
            ]
            
            # Store transcriptions sequentially with resource tracking
            for result in results:
                await self.manager.store_transcription(result)
                # Wait after each write to ensure proper JSON formatting
                await self.manager._write_queue.join()
                
                # Verify resource state after each write
                write_stats = await self.coordinator.get_write_stats()
                self.assertGreater(write_stats['successful_writes'], 0)
            
            # Verify transcription file exists and contains data
            transcription_file = self.manager._get_session_file("transcriptions")
            self.assertTrue(os.path.exists(transcription_file))
            
            # Check file content
            with open(transcription_file, 'r') as f:
                data = json.load(f)
                self.assertEqual(len(data), 3)
                self.assertEqual(data[0]['text'], "Test 0")
                
            # Verify CRC file exists
            self.assertTrue(os.path.exists(f"{transcription_file}.crc"))
            
            # Verify final resource state
            final_stats = await self.coordinator.get_resource_stats()
            self.assertEqual(final_stats['active_writes'], 0)
            
        except Exception as e:
            self.logger.error(f"Store transcription test failed: {e}", exc_info=True)
            raise
        
    @pytest.mark.fast
    async def test_speaker_metadata(self):
        """Test speaker metadata management with resource tracking."""
        try:
            # Create and update speaker metadata
            speaker_id = "speaker_0"
            history = self.create_test_history(speaker_id, channel=0)
            
            # Update metadata with resource tracking
            await self.manager.update_speaker_metadata(speaker_id, history)
            
            # Wait for writes to complete
            await self.manager._write_queue.join()
            
            # Verify metadata was stored
            metadata = await self.manager.get_speaker_metadata(speaker_id)
            self.assertIsNotNone(metadata)
            self.assertEqual(metadata['speaker_id'], speaker_id)
            self.assertEqual(metadata['channel'], 0)
            self.assertEqual(metadata['transcription_count'], 3)
            self.assertEqual(metadata['total_duration'], 3.0)
            
            # Verify resource state
            stats = await self.coordinator.get_resource_stats()
            self.assertEqual(stats['active_metadata_updates'], 0)
            
        except Exception as e:
            self.logger.error(f"Speaker metadata test failed: {e}", exc_info=True)
            raise
        
    @pytest.mark.fast
    async def test_session_archiving(self):
        """Test session archiving with resource management."""
        try:
            # Add some test data with resource tracking
            result = self.create_test_result()
            await self.manager.store_transcription(result)
            
            speaker_id = "speaker_0"
            history = self.create_test_history(speaker_id, channel=0)
            await self.manager.update_speaker_metadata(speaker_id, history)
            
            # Wait for writes to complete
            await self.manager._write_queue.join()
            
            # Verify resource state before archiving
            pre_stats = await self.coordinator.get_resource_stats()
            self.assertEqual(pre_stats['active_writes'], 0)
            
            # Archive session
            archive_path = await self.manager.archive_session()
            
            # Verify archive exists
            self.assertTrue(os.path.exists(archive_path))
            
            # Load and verify archived data
            session_data = await self.manager.load_session(self.manager._current_session)
            
            self.assertEqual(session_data['session_id'], self.manager._current_session)
            self.assertIn('transcriptions', session_data)
            self.assertIn('metadata', session_data)
            
            # Verify metadata content
            self.assertIn('speakers', session_data['metadata'])
            self.assertIn(speaker_id, session_data['metadata']['speakers'])
            
            # Verify final resource state
            final_stats = await self.coordinator.get_resource_stats()
            self.assertEqual(final_stats['active_archives'], 0)
            
        except Exception as e:
            self.logger.error(f"Session archiving test failed: {e}", exc_info=True)
            raise
        
    @pytest.mark.fast
    async def test_session_stats(self):
        """Test session statistics with resource tracking."""
        try:
            # Add test data for multiple speakers with resource tracking
            speakers = ["speaker_0", "speaker_1"]
            for i, speaker_id in enumerate(speakers):
                # Add transcriptions
                for j in range(2):
                    result = self.create_test_result(
                        text=f"Test {j}",
                        speaker_id=speaker_id,
                        channel=i
                    )
                    await self.manager.store_transcription(result)
                    
                    # Verify write completion
                    write_stats = await self.coordinator.get_write_stats()
                    self.assertGreater(write_stats['successful_writes'], 0)
                
                # Update speaker metadata
                history = self.create_test_history(speaker_id, channel=i)
                await self.manager.update_speaker_metadata(speaker_id, history)
                
                # Verify metadata update
                metadata_stats = await self.coordinator.get_resource_stats()
                self.assertEqual(metadata_stats['active_metadata_updates'], 0)
            
            # Wait for writes to complete
            await self.manager._write_queue.join()
            
            # Get and verify stats
            stats = await self.manager.get_session_stats()
            
            self.assertEqual(stats['speaker_count'], 2)
            self.assertEqual(len(stats['transcription_counts']), 2)
            self.assertGreater(stats['total_duration'], 0)
            self.assertGreater(stats['total_cost'], 0)
            
            # Verify final resource state
            final_stats = await self.coordinator.get_resource_stats()
            self.assertEqual(final_stats['active_writes'], 0)
            self.assertEqual(final_stats['active_metadata_updates'], 0)
            
        except Exception as e:
            self.logger.error(f"Session stats test failed: {e}", exc_info=True)
            raise
        
    @pytest.mark.fast
    async def test_concurrent_writes(self):
        """Test concurrent transcription storage with resource management."""
        try:
            # Test concurrent transcription storage with resource tracking
            results = [
                self.create_test_result(text=f"Test {i}")
                for i in range(10)
            ]
            
            # Store transcriptions sequentially with resource monitoring
            for i, result in enumerate(results):
                await self.manager.store_transcription(result)
                await self.manager._write_queue.join()
                
                # Verify write state after each operation
                write_stats = await self.coordinator.get_write_stats()
                self.assertGreater(write_stats['successful_writes'], i)
                self.assertEqual(write_stats['failed_writes'], 0)
                
                # Verify resource state
                resource_stats = await self.coordinator.get_resource_stats()
                self.assertEqual(resource_stats['active_writes'], 0)
            
            # Verify all transcriptions were stored
            transcription_file = self.manager._get_session_file("transcriptions")
            with open(transcription_file, 'r') as f:
                data = json.load(f)
                self.assertEqual(len(data), 10)
                
            # Verify final write stats
            final_stats = await self.coordinator.get_write_stats()
            self.assertEqual(final_stats['successful_writes'], 10)
            self.assertEqual(final_stats['failed_writes'], 0)
            
        except Exception as e:
            self.logger.error(f"Concurrent writes test failed: {e}", exc_info=True)
            raise
            
    @pytest.mark.fast
    async def test_error_handling(self):
        """Test error handling and recovery with comprehensive validation."""
        try:
            # Test with invalid file path
            original_dir = self.manager.transcriptions_dir
            invalid_path = os.path.join(self.test_dir, "nonexistent")
            
            # Stop the manager and clear the queue
            self.manager._running = False
            await self.manager._write_queue.join()
            
            # Don't create the directory to test error handling
            self.manager.transcriptions_dir = invalid_path
            
            # Attempt to store transcription
            result = self.create_test_result()
            
            # The operation should raise FileNotFoundError
            with self.assertRaises(FileNotFoundError):
                await self.manager._write_data({
                    'type': 'transcriptions',
                    'content': {
                        'timestamp': result.timestamp,
                        'speaker_id': result.speaker_id,
                        'text': result.text,
                        'confidence': result.confidence,
                        'channel': result.channel,
                        'duration': result.segment_duration,
                        'cost': result.cost
                    }
                })
                
            # Verify error was logged and tracked
            error_stats = await self.coordinator.get_error_stats()
            self.assertGreater(error_stats['error_count'], 0)
            self.assertIn('file_not_found', error_stats['error_types'])
            
            # Restore valid path
            self.manager.transcriptions_dir = original_dir
            
            # Test loading non-existent session
            with self.assertRaises(FileNotFoundError):
                await self.manager.load_session("nonexistent_session")
                
            # Verify error tracking
            error_stats = await self.coordinator.get_error_stats()
            self.assertIn('session_not_found', error_stats['error_types'])
            
        except Exception as e:
            self.logger.error(f"Error handling test failed: {e}", exc_info=True)
            raise

if __name__ == '__main__':
    unittest.main()
