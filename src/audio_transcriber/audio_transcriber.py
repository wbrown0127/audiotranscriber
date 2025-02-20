"""
COMPONENT_NOTES:
{
    "name": "AudioTranscriber",
    "type": "Core Application",
    "description": "Main audio transcription system that coordinates audio capture, processing, and transcription with thread-safe monitoring and cleanup",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                AT[AudioTranscriber] --> MC[MonitoringCoordinator]
                AT --> CC[CleanupCoordinator]
                AT --> WM[WindowsManager]
                AT --> AC[AdaptiveAudioCapture]
                AT --> SP[SignalProcessor]
                AT --> SM[StorageManager]
                AT --> WT[WhisperTranscriber]
        ```",
        "dependencies": {
            "MonitoringCoordinator": "Manages system monitoring and state",
            "CleanupCoordinator": "Coordinates orderly system cleanup",
            "WindowsManager": "Handles Windows-specific operations",
            "AdaptiveAudioCapture": "Manages audio device capture",
            "SignalProcessor": "Processes captured audio data",
            "StorageManager": "Handles audio data storage",
            "WhisperTranscriber": "Performs audio transcription"
        }
    },
    "notes": [
        "Implements coordinated initialization and cleanup",
        "Provides comprehensive system health monitoring",
        "Handles resource management and limits",
        "Supports recovery from system failures",
        "Uses ordered cleanup phases for safe shutdown"
    ]
}

"""

import asyncio
import os
import time
import psutil
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass
import json
import logging
from datetime import datetime

from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.signal_processor import SignalProcessor
from audio_transcriber.storage_manager import StorageManager
from audio_transcriber.windows_manager import WindowsManager
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.cleanup_coordinator import CleanupCoordinator, CleanupStep, CleanupPhase
from audio_transcriber.whisper_transcriber import WhisperTranscriber # Import WhisperTranscriber

@dataclass
class SystemStatus:
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    temperature: Optional[float]
    stream_health: bool
    api_status: bool

class AudioTranscriber:
    def __init__(self, base_path: str):
        self.base_path = base_path
        self.setup_directories()
        self.setup_logging()
        
        # Initialize coordinators
        self.coordinator = MonitoringCoordinator()
        self._setup_cleanup_coordinator()
        
        # Initialize components with coordinator
        self.windows = WindowsManager()
        self.capture = AdaptiveAudioCapture(self.coordinator)
        self.processor = SignalProcessor()
        self.storage = StorageManager(os.path.join(base_path, "recordings"))
        self.whisper_transcriber = WhisperTranscriber() # Initialize WhisperTranscriber
        
        # Constants
        self.max_errors = 3
        
    def _setup_cleanup_coordinator(self):
        """Initialize cleanup coordinator with ordered steps."""
        self.cleanup_coordinator = CleanupCoordinator(self.coordinator)
        
        # Register cleanup steps with dependencies
        self.cleanup_coordinator.register_cleanup_step(
            CleanupStep(
                name="request_shutdown",
                phase=CleanupPhase.INITIATING,
                dependencies=set(),
                cleanup_fn=lambda: asyncio.create_task(self._async_request_shutdown()),
                verification_fn=lambda: asyncio.create_task(self._async_verify_shutdown())
            )
        )
        
        self.cleanup_coordinator.register_cleanup_step(
            CleanupStep(
                name="stop_monitoring",
                phase=CleanupPhase.INITIATING,
                dependencies={"request_shutdown"},
                cleanup_fn=lambda: asyncio.create_task(self._async_stop_monitoring()),
                verification_fn=self._verify_monitoring_stopped
            )
        )
        
        self.cleanup_coordinator.register_cleanup_step(
            CleanupStep(
                name="stop_capture",
                phase=CleanupPhase.STOPPING_CAPTURE,
                dependencies={"stop_monitoring"},
                cleanup_fn=lambda: asyncio.create_task(self._stop_capture_with_lock()),
                verification_fn=self._verify_capture_stopped
            )
        )
        
        self.cleanup_coordinator.register_cleanup_step(
            CleanupStep(
                name="flush_storage",
                phase=CleanupPhase.FLUSHING_STORAGE,
                dependencies={"stop_capture"},
                cleanup_fn=lambda: asyncio.create_task(self._flush_storage_with_lock()),
                verification_fn=self._verify_storage_flushed
            )
        )
        
        self.cleanup_coordinator.register_cleanup_step(
            CleanupStep(
                name="cleanup_backups",
                phase=CleanupPhase.RELEASING_RESOURCES,
                dependencies={"flush_storage"},
                cleanup_fn=lambda: asyncio.create_task(self._async_cleanup_backups()),
                verification_fn=self._verify_backups_cleaned
            )
        )
        
        self.cleanup_coordinator.register_cleanup_step(
            CleanupStep(
                name="close_logs",
                phase=CleanupPhase.CLOSING_LOGS,
                dependencies={"cleanup_backups"},
                cleanup_fn=lambda: asyncio.create_task(self._close_log_handlers()),
                verification_fn=self._verify_logs_closed
            )
        )
        
    def setup_directories(self):
        """Create necessary directories."""
        dirs = [
            os.path.join(self.base_path, d)
            for d in ["recordings", "logs", "temp", "backup"]
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            
    def setup_logging(self):
        """Configure logging system."""
        log_file = os.path.join(
            self.base_path, 
            "logs", 
            f"transcriber_{datetime.now():%Y%m%d_%H%M%S}.log"
        )
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("AudioTranscriber")
        
    async def _init_component(self, component: Any, name: str) -> bool:
        """Initialize a single component with verification."""
        try:
            if hasattr(component, 'initialize'):
                await component.initialize()
            elif hasattr(component, 'start_capture'):
                if not component.start_capture():
                    raise RuntimeError(f"Failed to start {name}")
            elif hasattr(component, 'setup_mmcss'):
                if not component.setup_mmcss():
                    self.logger.warning(f"{name} setup failed, using fallback configuration")
                    
            # Verify component health
            if hasattr(component, 'get_performance_stats'):
                stats = component.get_performance_stats()
                self.logger.info(f"{name} initialized with stats: {stats}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize {name}: {e}")
            return False
            
    async def _rollback_initialization(self, components: list, current_index: int) -> None:
        """Rollback initialization for components in reverse order."""
        for component, name in reversed(components[:current_index + 1]):
            try:
                if hasattr(component, 'stop_capture'):
                    component.stop_capture()
                elif hasattr(component, 'cleanup'):
                    await component.cleanup()
                self.logger.info(f"Rolled back {name}")
            except Exception as e:
                self.logger.error(f"Error during rollback of {name}: {e}")

    async def initialize(self) -> bool:
        """Initialize all components with proper dependency ordering and rollback."""
        # Define components in dependency order
        components = [
            (self.windows, "Windows Manager"),      # Base system checks
            (self.storage, "Storage Manager"),      # File system operations
            (self.processor, "Signal Processor"),   # Audio processing
            (self.capture, "Audio Capture")         # Device capture
        ]
        
        try:
            # System compatibility check
            system_info = self.windows.get_system_info()
            self.logger.info(f"System Info: {system_info}")
            
            # Initialize each component in order
            for i, (component, name) in enumerate(components):
                self.logger.info(f"Initializing {name}...")
                if not await self._init_component(component, name):
                    self.logger.error(f"Initialization failed at {name}")
                    await self._rollback_initialization(components, i)
                    return False
                    
            # Start monitoring last after all components are ready
            self.coordinator.start_monitoring()
            if not self.coordinator.is_monitoring_active():
                self.logger.error("Failed to start monitoring")
                await self._rollback_initialization(components, len(components) - 1)
                return False
                
            self.logger.info("System initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            await self._rollback_initialization(components, len(components) - 1)
            return False
            
    async def run(self):
        """Main processing loop."""
        try:
            if not await self.initialize():
                return
                
            self.logger.info("Starting audio processing")
            
            while not self.coordinator.is_shutdown_requested():
                try:
                    # Get audio data
                    audio_data = self.capture.get_audio_data()
                    if audio_data is None:
                        continue
                        
                    # Process audio with thread safety
                    with self.coordinator.processor_lock():
                        processed_data, stats = self.processor.process_audio(
                            audio_data.tobytes(),
                            width=2
                        )
                    
                    if stats:
                        # Store processed audio with thread safety
                        with self.coordinator.storage_lock():
                            filename = os.path.join(
                                self.storage.base_path,
                                f"audio_{int(time.time())}.raw"
                            )
                            await self.storage.optimized_write(processed_data, filename)
                        
                        # Transcribe audio chunk and print result
                        transcription_text = self.whisper_transcriber.transcribe_audio_chunk(processed_data)
                        if transcription_text:
                            self.logger.info(f"Transcription: {transcription_text.strip()}")
                    
                    # Periodic health check
                    await self.check_system_health()
                    
                except Exception as e:
                    self.logger.error(f"Processing error: {e}")
                    error_count = self.coordinator.increment_error_count()
                    
                    if error_count >= self.max_errors:
                        self.logger.critical("Too many errors, initiating recovery")
                        await self.attempt_recovery()
                        
        except Exception as e:
            self.logger.critical(f"Fatal error: {e}")
            raise
            
        finally:
            await self.cleanup()
            
    # Resource limits
    RESOURCE_LIMITS = {
        'cpu_usage': 80.0,  # Max CPU usage percentage
        'memory_usage': 75.0,  # Max memory usage percentage
        'disk_usage': 90.0,  # Max disk usage percentage
        'buffer_size': 1024 * 1024,  # 1MB max buffer size
        'buffer_duration': 60.0,  # 60 seconds max buffer duration
        'temperature': 85.0  # Max temperature in Celsius
    }
    
    def _check_resource_limits(self, stats: Dict[str, Any]) -> bool:
        """Check if any resource limits are exceeded."""
        violations = []
        
        if stats.get('cpu_usage', 0) > self.RESOURCE_LIMITS['cpu_usage']:
            violations.append(f"CPU usage ({stats['cpu_usage']}%) exceeds limit ({self.RESOURCE_LIMITS['cpu_usage']}%)")
            
        if stats.get('memory_usage', 0) > self.RESOURCE_LIMITS['memory_usage']:
            violations.append(f"Memory usage ({stats['memory_usage']}%) exceeds limit ({self.RESOURCE_LIMITS['memory_usage']}%)")
            
        if stats.get('disk_usage', 0) > self.RESOURCE_LIMITS['disk_usage']:
            violations.append(f"Disk usage ({stats['disk_usage']}%) exceeds limit ({self.RESOURCE_LIMITS['disk_usage']}%)")
            
        if stats.get('buffer_size', 0) > self.RESOURCE_LIMITS['buffer_size']:
            violations.append(f"Buffer size ({stats['buffer_size']} bytes) exceeds limit ({self.RESOURCE_LIMITS['buffer_size']} bytes)")
            
        if stats.get('buffer_duration_ms', 0) > self.RESOURCE_LIMITS['buffer_duration'] * 1000:
            violations.append(f"Buffer duration ({stats['buffer_duration_ms']}ms) exceeds limit ({self.RESOURCE_LIMITS['buffer_duration'] * 1000}ms)")
            
        if stats.get('temperature') and stats['temperature'] > self.RESOURCE_LIMITS['temperature']:
            violations.append(f"Temperature ({stats['temperature']}°C) exceeds limit ({self.RESOURCE_LIMITS['temperature']}°C)")
            
        if violations:
            self.logger.warning("Resource limit violations detected:\n" + "\n".join(violations))
            return False
        return True
    
    async def check_system_health(self):
        """Monitor system health metrics with coordinated lock ordering."""
        if not self.coordinator.should_check_health():
            return
            
        try:
            # Use component_lock for coordinated access
            async with self.coordinator.component_lock():
                # Get performance stats from all components in a consistent order
                stats = await asyncio.gather(
                    self.capture.get_performance_stats(),
                    self.processor.get_performance_stats(),
                    self.storage.get_performance_stats()
                )
                capture_stats, processor_stats, storage_stats = stats
                
                # Check resource limits
                components_health = all(
                    self._check_resource_limits(component_stats)
                    for component_stats in stats
                )
                
                # Update coordinator state
                self.coordinator.update_state(
                    cpu_usage=capture_stats['cpu_usage'],
                    memory_usage=processor_stats['memory_usage'],
                    disk_usage=storage_stats['buffer_usage'],
                    temperature=capture_stats.get('temperature'),
                    api_status=not self.windows.fallback_enabled
                )
                
                # Update performance stats with defaults if missing
                capture_stats_with_defaults = {
                    'cpu_usage': capture_stats.get('cpu_usage', 0.0),
                    'temperature': capture_stats.get('temperature', None),
                    'stream_health': capture_stats.get('stream_health', True) and components_health,
                    'buffer_size': capture_stats.get('buffer_size', 480),
                    'buffer_duration_ms': capture_stats.get('buffer_duration_ms', 30.0)
                }
                
                # Update performance stats
                self.coordinator.update_performance_stats('capture', capture_stats_with_defaults)
                self.coordinator.update_performance_stats('processor', processor_stats)
                self.coordinator.update_performance_stats('storage', storage_stats)
                
                # Log system status
                self.logger.info(f"System Status: {self.coordinator.get_state()}")
                
                # Save detailed stats
                await self.save_performance_stats(self.coordinator.get_performance_stats())
                
                # Trigger recovery if resource limits are exceeded
                if not components_health:
                    self.logger.warning("Resource limits exceeded, incrementing error count")
                    error_count = self.coordinator.increment_error_count()
                    if error_count >= self.max_errors:
                        self.logger.critical("Resource limits exceeded max errors, initiating recovery")
                        await self.attempt_recovery()
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            
    async def save_performance_stats(self, stats: Dict[str, Any]):
        """Save performance statistics to file."""
        try:
            stats_file = os.path.join(
                self.base_path,
                "logs",
                f"performance_{datetime.now():%Y%m%d}.json"
            )
            
            async with aiofiles.open(stats_file, 'a') as f:
                await f.write(json.dumps(stats) + '\n')
                
        except Exception as e:
            self.logger.error(f"Failed to save performance stats: {e}")
            
    @dataclass
    class RecoveryStep:
        """Represents a recovery step with verification."""
        name: str
        action: callable
        verify: callable
        timeout: float
        required: bool = True
        
    async def _execute_recovery_step(self, step: RecoveryStep) -> bool:
        """Execute a single recovery step with timeout and verification."""
        self.logger.info(f"Recovery step: {step.name}")
        try:
            await step.action()
            if await self._verify_with_timeout(step.verify, step.timeout):
                self.logger.info(f"Recovery step {step.name} succeeded")
                return True
            else:
                self.logger.error(f"Recovery step {step.name} verification timed out")
                return False
        except Exception as e:
            self.logger.error(f"Recovery step {step.name} failed: {e}")
            return False
            
    async def attempt_recovery(self):
        """Attempt system recovery with partial recovery support."""
        self.logger.info("Starting recovery process")
        recovery_steps = []
        successful_steps = []
        
        try:
            # Define recovery steps in order
            recovery_steps = [
                self.RecoveryStep(
                    name="Stop Capture",
                    action=lambda: self.capture.stop_capture(),
                    verify=lambda: not self.capture.is_active(),
                    timeout=self.VERIFY_TIMEOUT,
                    required=True
                ),
                self.RecoveryStep(
                    name="Flush Storage",
                    action=lambda: self.storage.emergency_flush(),
                    verify=lambda: self.storage.get_buffer_size() == 0,
                    timeout=self.EMERGENCY_TIMEOUT,
                    required=True
                ),
                self.RecoveryStep(
                    name="Reset Monitoring",
                    action=lambda: self.coordinator.stop_monitoring(),
                    verify=lambda: not self.coordinator.is_monitoring_active(),
                    timeout=self.VERIFY_TIMEOUT,
                    required=True
                ),
                self.RecoveryStep(
                    name="Check Windows System",
                    action=lambda: self.windows.setup_mmcss(),
                    verify=lambda: not self.windows.fallback_enabled,
                    timeout=self.VERIFY_TIMEOUT,
                    required=False
                ),
                self.RecoveryStep(
                    name="Initialize Storage",
                    action=lambda: self.storage.initialize(),
                    verify=lambda: self.storage.get_buffer_size() == 0,
                    timeout=self.VERIFY_TIMEOUT,
                    required=True
                ),
                self.RecoveryStep(
                    name="Start Monitoring",
                    action=lambda: self.coordinator.start_monitoring(),
                    verify=lambda: self.coordinator.is_monitoring_active(),
                    timeout=self.VERIFY_TIMEOUT,
                    required=True
                ),
                self.RecoveryStep(
                    name="Start Capture",
                    action=lambda: self.capture.start_capture(),
                    verify=lambda: self.capture.is_active(),
                    timeout=self.VERIFY_TIMEOUT,
                    required=True
                )
            ]
            
            # Execute recovery steps
            for step in recovery_steps:
                with self.coordinator.component_lock():
                    if await self._execute_recovery_step(step):
                        successful_steps.append(step)
                    elif step.required:
                        raise RuntimeError(f"Required recovery step failed: {step.name}")
                    else:
                        self.logger.warning(f"Optional recovery step failed: {step.name}")
                        
            # Verify final system state
            state = self.coordinator.get_state()
            if not state.stream_health:
                raise RuntimeError("Stream health check failed after recovery")
                
            # Reset error tracking
            self.coordinator.reset_error_count()
            self.logger.info(f"Recovery completed successfully ({len(successful_steps)}/{len(recovery_steps)} steps)")
            return True
            
        except Exception as e:
            error_msg = f"Recovery failed: {str(e)}"
            self.logger.critical(error_msg)
            
            # Update state with recovery attempt
            self.coordinator.update_state(
                stream_health=False,
                recovery_attempts=self.coordinator.get_state().recovery_attempts + 1
            )
            
            # Attempt rollback of successful steps in reverse order
            self.logger.info("Attempting rollback of successful steps")
            for step in reversed(successful_steps):
                try:
                    if hasattr(step, 'rollback'):
                        await step.rollback()
                except Exception as rollback_error:
                    self.logger.error(f"Rollback failed for {step.name}: {rollback_error}")
                    
            raise RuntimeError(error_msg)

    async def _stop_capture_with_lock(self):
        """Stop audio capture with thread safety."""
        with self.coordinator.capture_lock():
            self.capture.stop_capture()

    async def _flush_storage_with_lock(self):
        """Flush storage buffers with thread safety."""
        with self.coordinator.storage_lock():
            await self.storage.emergency_flush()

    async def _close_log_handlers(self):
        """Close all log handlers."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        logging.shutdown()

    # Cleanup timeouts
    VERIFY_TIMEOUT = 5.0  # 5 seconds timeout for verifications
    EMERGENCY_TIMEOUT = 10.0  # 10 seconds timeout for emergency operations
    
    async def _verify_with_timeout(self, verify_fn: callable, timeout: float) -> bool:
        """Run verification function with timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if await verify_fn():
                return True
            await asyncio.sleep(0.1)  # Prevent CPU spinning
        return False

    async def _verify_monitoring_stopped(self) -> bool:
        """Verify monitoring system is stopped with timeout."""
        async def check_monitoring():
            return not hasattr(self.coordinator, '_monitoring_thread') or \
                   not self.coordinator._monitoring_thread.is_alive()
        return await self._verify_with_timeout(check_monitoring, self.VERIFY_TIMEOUT)

    async def _verify_capture_stopped(self) -> bool:
        """Verify audio capture is stopped with timeout."""
        async def check_capture():
            return not self.capture.is_active()
        return await self._verify_with_timeout(check_capture, self.VERIFY_TIMEOUT)

    async def _verify_storage_flushed(self) -> bool:
        """Verify storage buffers are flushed with timeout."""
        async def check_storage():
            return self.storage.get_buffer_size() == 0
        return await self._verify_with_timeout(check_storage, self.EMERGENCY_TIMEOUT)

    async def _verify_backups_cleaned(self) -> bool:
        """Verify old backups are cleaned up with timeout."""
        async def check_backups():
            backup_dir = os.path.join(self.base_path, "backup")
            return len(os.listdir(backup_dir)) == 0
        return await self._verify_with_timeout(check_backups, self.VERIFY_TIMEOUT)

    async def _verify_logs_closed(self) -> bool:
        """Verify all log handlers are closed with timeout."""
        async def check_logs():
            root_logger = logging.getLogger()
            return len(root_logger.handlers) == 0 and len(self.logger.handlers) == 0
        return await self._verify_with_timeout(check_logs, self.VERIFY_TIMEOUT)

    async def _async_request_shutdown(self):
        """Async wrapper for request_shutdown."""
        self.coordinator.request_shutdown()
        await asyncio.sleep(0)  # Allow other tasks to run

    async def _async_verify_shutdown(self) -> bool:
        """Async verification of shutdown."""
        return self.coordinator.is_shutdown_requested()

    async def _async_stop_monitoring(self):
        """Async wrapper for stop_monitoring."""
        self.coordinator.stop_monitoring()
        await asyncio.sleep(0)  # Allow other tasks to run

    async def _async_cleanup_backups(self):
        """Async wrapper for cleanup_old_backups."""
        await self.storage.cleanup_old_backups()
            
    async def cleanup(self):
        """Clean up resources using coordinated cleanup process."""
        self.logger.info("Starting coordinated cleanup")
        
        try:
            # Execute cleanup steps in order
            cleanup_success = await self.cleanup_coordinator.execute_cleanup()
            
            if cleanup_success:
                self.logger.info("Cleanup completed successfully")
            else:
                self.logger.error("Cleanup completed with failures")
                cleanup_status = self.cleanup_coordinator.get_cleanup_status()
                self.logger.error(f"Cleanup status: {cleanup_status}")
            
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")
            raise
            
    def get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        state = self.coordinator.get_state()
        perf_stats = self.coordinator.get_performance_stats()
        cleanup_status = self.cleanup_coordinator.get_cleanup_status()
        
        # Ensure capture component is always present
        components = perf_stats.copy()
        if 'capture' not in components:
            components['capture'] = {
                'cpu_usage': 0.0,
                'temperature': None,
                'stream_health': True,
                'buffer_size': 480,
                'buffer_duration_ms': 30.0
            }
        
        return {
            'system_status': state,
            'error_count': state.error_count,
            'uptime': time.time() - self.coordinator._last_health_check,
            'components': components,
            'cleanup_status': cleanup_status
        }

async def main():
    base_path = os.path.abspath(os.path.dirname(__file__))
    transcriber = AudioTranscriber(base_path)
    
    try:
        await transcriber.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await transcriber.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
