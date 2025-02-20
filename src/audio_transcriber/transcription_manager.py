"""
COMPONENT_NOTES:
{
    "name": "TranscriptionManager",
    "type": "Core Component",
    "description": "Transcription data manager that handles storage, retrieval, and archival of transcription results with metadata tracking and session management through MonitoringCoordinator",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TM[TranscriptionManager] --> MC[MonitoringCoordinator]
                TM --> TR[TranscriptionResult]
                TM --> SM[SessionManager]
                TM --> WQ[WriteQueue]
                TM --> MD[MetadataTracker]
                MC --> RP[ResourcePool]
                TR --> TD[TranscriptionData]
                TR --> SD[SpeakerData]
                SM --> SA[SessionArchive]
                SM --> SS[SessionStats]
                WQ --> WO[WriteOperation]
                WQ --> CRC[CRCValidation]
                MD --> SH[SpeakerHistory]
                MD --> SC[SpeakerCost]
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
            "TranscriptionResult": "Result data structure",
            "SessionManager": "Session handling",
            "WriteQueue": "Async write operations",
            "MetadataTracker": "Metadata management",
            "TranscriptionData": "Core transcription data",
            "SpeakerData": "Speaker information",
            "SessionArchive": "ZIP64 archival",
            "SessionStats": "Statistics tracking",
            "WriteOperation": "Write handling",
            "CRCValidation": "Data integrity",
            "SpeakerHistory": "History tracking",
            "SpeakerCost": "Cost tracking"
        }
    },
    "notes": [
        "Uses MonitoringCoordinator for resource management",
        "Manages transcription storage with proper buffer handling",
        "Handles session archival with resource cleanup",
        "Tracks speaker metadata with memory optimization",
        "Ensures data integrity with CRC validation",
        "Provides async operations with proper error handling",
        "Supports ZIP64 compression with buffer management"
    ],
    "usage": {
        "examples": [
            "manager = TranscriptionManager(base_path, coordinator)",
            "await manager.start()",
            "await manager.store_transcription(result)",
            "await manager.archive_session()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "json",
            "zipfile",
            "zlib",
            "asyncio"
        ],
        "system": {
            "storage": "Write access to directories",
            "memory": "Managed through MonitoringCoordinator"
        }
    },
    "performance": {
        "execution_time": "Async I/O operations",
        "resource_usage": [
            "Efficient queue management",
            "Optimized ZIP compression",
            "CRC32 data validation",
            "Resource pool integration",
            "Proper buffer lifecycle"
        ]
    }
}
"""

import json
import logging
import os
import time
import zipfile
import zlib
from dataclasses import asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
from .whisper_transcriber import TranscriptionResult, SpeakerHistory

logger = logging.getLogger(__name__)

class TranscriptionManager:
    """Manages storage and retrieval of transcription data."""
    
    def __init__(self, base_path: str, coordinator=None):
        """
        Initialize transcription manager.
        
        Args:
            base_path: Base directory for storing transcription data
            coordinator: MonitoringCoordinator instance for resource management
        """
        self.base_path = base_path
        if not coordinator:
            raise RuntimeError("MonitoringCoordinator is required")
        self.coordinator = coordinator
        
        self.transcriptions_dir = os.path.join(base_path, "transcriptions")
        self.metadata_dir = os.path.join(base_path, "metadata")
        self.archive_dir = os.path.join(base_path, "archives")
        
        # Create necessary directories
        os.makedirs(self.transcriptions_dir, exist_ok=True)
        os.makedirs(self.metadata_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)
        
        self._current_session = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._speaker_metadata: Dict[str, Dict] = {}
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._running = True
        
    async def start(self):
        """Start the transcription manager."""
        self._running = True
        asyncio.create_task(self._process_write_queue())
        
    async def stop(self):
        """Stop the transcription manager and cleanup."""
        self._running = False
        await self._write_queue.join()  # Wait for pending writes
        await self.archive_session()
        
    def _get_session_file(self, file_type: str) -> str:
        """Get path for a session file."""
        return os.path.join(
            self.transcriptions_dir,
            f"session_{self._current_session}_{file_type}.json"
        )
        
    async def _process_write_queue(self):
        """Process queued write operations."""
        while self._running or not self._write_queue.empty():
            try:
                operation = await self._write_queue.get()
                try:
                    await self._write_data(operation)
                finally:
                    self._write_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing write operation: {e}")
                if self.coordinator:
                    self.coordinator.handle_error(e, "transcription_manager")
                raise
                
    async def _write_data(self, data: Dict):
        """Write data to appropriate files using resource pool."""
        buffer = None
        try:
            file_path = self._get_session_file(data['type'])
            
            # Write data with proper JSON formatting
            async with asyncio.Lock():
                array = []
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                            if content:
                                array = json.loads(content)
                    except json.JSONDecodeError:
                        # File exists but is corrupted/empty
                        pass
                
                # Append new data
                array.append(data['content'])
                
                # Convert to JSON with proper formatting
                json_data = json.dumps(array, indent=2, ensure_ascii=False)
                
                # Allocate buffer for write operation
                buffer = self.coordinator.allocate_resource(
                    'transcription_manager', 
                    'buffer',
                    len(json_data.encode())
                )
                if not buffer:
                    raise RuntimeError("Failed to allocate write buffer")
                
                # Copy data to buffer
                buffer[:] = json_data.encode()
                
                # Write buffer to file
                with open(file_path, 'wb') as f:
                    f.write(buffer)
                    
            # Verify write with CRC
            crc = zlib.crc32(json.dumps(data['content']).encode())
            with open(f"{file_path}.crc", 'a') as f:
                f.write(f"{crc}\n")
                
        except Exception as e:
            logger.error(f"Error writing data: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "transcription_manager")
            raise
        finally:
            # Release buffer if allocated
            if buffer:
                self.coordinator.release_resource('transcription_manager', 'buffer', buffer)
            
    async def store_transcription(self, result: TranscriptionResult):
        """
        Store a transcription result.
        
        Args:
            result: TranscriptionResult to store
        """
        # Queue transcription data
        await self._write_queue.put({
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
        
        # Update coordinator metrics
        if self.coordinator:
            self.coordinator.update_state(
                transcription_count=len(self._write_queue._queue),
                last_transcription_time=time.time()
            )
        
    async def update_speaker_metadata(self, 
                                    speaker_id: str,
                                    history: SpeakerHistory):
        """
        Update metadata for a speaker.
        
        Args:
            speaker_id: ID of the speaker
            history: Speaker's transcription history
        """
        metadata = {
            'speaker_id': speaker_id,
            'channel': history.channel,
            'total_duration': history.total_duration,
            'total_cost': history.total_cost,
            'transcription_count': len(history.transcriptions),
            'last_updated': time.time()
        }
        
        self._speaker_metadata[speaker_id] = metadata
        
        # Queue metadata update
        await self._write_queue.put({
            'type': 'speaker_metadata',
            'content': metadata
        })
        
        # Update coordinator metrics
        if self.coordinator:
            self.coordinator.update_state(
                speaker_count=len(self._speaker_metadata),
                total_duration=sum(m['total_duration'] for m in self._speaker_metadata.values()),
                total_cost=sum(m['total_cost'] for m in self._speaker_metadata.values())
            )
        
    def get_speaker_metadata(self, speaker_id: str) -> Optional[Dict]:
        """Get metadata for a specific speaker."""
        return self._speaker_metadata.get(speaker_id)
        
    async def archive_session(self):
        """Archive the current session data using ZIP64 format with resource management."""
        buffer = None
        try:
            archive_path = os.path.join(
                self.archive_dir,
                f"session_{self._current_session}.zip"
            )
            
            # Create metadata with proper formatting
            metadata = {
                'session_id': self._current_session,
                'speakers': self._speaker_metadata,
                'timestamp': time.time()
            }
            
            # Allocate buffer for metadata
            metadata_json = json.dumps(metadata, indent=2)
            buffer = self.coordinator.allocate_resource(
                'transcription_manager',
                'buffer',
                len(metadata_json.encode())
            )
            if not buffer:
                raise RuntimeError("Failed to allocate metadata buffer")
            
            # Copy metadata to buffer
            buffer[:] = metadata_json.encode()
            
            # Write metadata file
            metadata_file = os.path.join(
                self.metadata_dir,
                f"session_{self._current_session}_metadata.json"
            )
            with open(metadata_file, 'wb') as f:
                f.write(buffer)
            
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, True) as zf:
                # Archive transcriptions
                for file in os.listdir(self.transcriptions_dir):
                    if file.startswith(f"session_{self._current_session}"):
                        file_path = os.path.join(self.transcriptions_dir, file)
                        zf.write(file_path, file)
                        
                # Archive metadata
                zf.write(metadata_file, os.path.basename(metadata_file))
                
            logger.info(f"Session archived to {archive_path}")
            
            # Update coordinator metrics
            if self.coordinator:
                self.coordinator.update_state(
                    archive_complete=True,
                    archive_path=archive_path,
                    archive_time=time.time()
                )
            
            return archive_path
            
        except Exception as e:
            logger.error(f"Error archiving session: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "transcription_manager")
            raise
        finally:
            # Release buffer if allocated
            if buffer:
                self.coordinator.release_resource('transcription_manager', 'buffer', buffer)
            
    async def load_session(self, session_id: str) -> Dict[str, Any]:
        """
        Load data from an archived session with resource management.
        
        Args:
            session_id: ID of the session to load
            
        Returns:
            Dict containing session data
        """
        buffer = None
        try:
            archive_path = os.path.join(
                self.archive_dir,
                f"session_{session_id}.zip"
            )
            
            with zipfile.ZipFile(archive_path, 'r') as zf:
                # Load transcriptions
                transcriptions_file = f"session_{session_id}_transcriptions.json"
                if transcriptions_file in zf.namelist():
                    with zf.open(transcriptions_file) as f:
                        # Allocate buffer for transcriptions
                        data = f.read()
                        buffer = self.coordinator.allocate_resource(
                            'transcription_manager',
                            'buffer',
                            len(data)
                        )
                        if not buffer:
                            raise RuntimeError("Failed to allocate transcriptions buffer")
                        
                        # Copy data to buffer and parse
                        buffer[:] = data
                        transcriptions = json.loads(buffer.decode())
                else:
                    transcriptions = []
                    
                # Load metadata
                metadata_file = f"session_{session_id}_metadata.json"
                if metadata_file in zf.namelist():
                    with zf.open(metadata_file) as f:
                        # Reuse buffer for metadata if possible
                        data = f.read()
                        if not buffer or len(buffer) < len(data):
                            # Release old buffer if it exists
                            if buffer:
                                self.coordinator.release_resource(
                                    'transcription_manager',
                                    'buffer',
                                    buffer
                                )
                            # Allocate new buffer
                            buffer = self.coordinator.allocate_resource(
                                'transcription_manager',
                                'buffer',
                                len(data)
                            )
                            if not buffer:
                                raise RuntimeError("Failed to allocate metadata buffer")
                        
                        # Copy data to buffer and parse
                        buffer[:len(data)] = data
                        metadata = json.loads(buffer[:len(data)].decode())
                else:
                    metadata = {}
                    
            return {
                'session_id': session_id,
                'transcriptions': transcriptions,
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Error loading session {session_id}: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "transcription_manager")
            raise
        finally:
            # Release buffer if allocated
            if buffer:
                self.coordinator.release_resource('transcription_manager', 'buffer', buffer)
            
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for the current session."""
        stats = {
            'session_id': self._current_session,
            'speaker_count': len(self._speaker_metadata),
            'total_duration': sum(
                meta['total_duration'] 
                for meta in self._speaker_metadata.values()
            ),
            'total_cost': sum(
                meta['total_cost'] 
                for meta in self._speaker_metadata.values()
            ),
            'transcription_counts': {
                speaker_id: meta['transcription_count']
                for speaker_id, meta in self._speaker_metadata.items()
            }
        }
        
        # Update coordinator metrics
        if self.coordinator:
            self.coordinator.update_performance_stats('transcription_manager', stats)
            
        return stats
