"""
COMPONENT_NOTES:
{
    "name": "MainApplication",
    "type": "Entry Point",
    "description": "Main entry point for the Audio Transcriber application that initializes components and launches the GUI interface",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                MA[MainApplication] --> QA[QApplication]
                MA --> MW[MainWindow]
                MA --> MC[MonitoringCoordinator]
                MA --> AC[AudioCapture]
                MA --> BM[BufferManager]
                MA --> SP[SignalProcessor]
                MA --> SM[StorageManager]
                MA --> AS[AlertSystem]
                MA --> WT[WhisperTranscriber]
                MA --> WM[WASAPIMonitor]
                MW --> MT[MonitoringTimer]
                MC --> AM[AlertMonitor]
                AC --> WC[WASAPICapture]
                BM --> BQ[BufferQueues]
                SP --> TA[TranscriptionAnalysis]
                SM --> SI[StorageInit]
        ```",
        "dependencies": {
            "QApplication": "Qt application",
            "MainWindow": "GUI interface",
            "MonitoringCoordinator": "System monitoring",
            "AudioCapture": "Audio input",
            "BufferManager": "Buffer handling",
            "SignalProcessor": "Audio processing",
            "StorageManager": "Data storage",
            "AlertSystem": "Alert handling",
            "WhisperTranscriber": "Transcription",
            "WASAPIMonitor": "Audio monitoring",
            "MonitoringTimer": "Status updates",
            "AlertMonitor": "Alert tracking",
            "WASAPICapture": "Audio capture",
            "BufferQueues": "Data queues",
            "TranscriptionAnalysis": "Text analysis",
            "StorageInit": "Storage setup"
        }
    }
}
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.buffer_manager import BufferManager
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.storage_manager import StorageManager
from audio_transcriber.signal_processor import SignalProcessor
# Note: Using renamed interface i_alert_system (2025-02-24 standardization)
from audio_transcriber.interfaces.i_alert_system import AlertSystem, AlertConfig
from audio_transcriber.gui.main_window import MainWindow
from audio_transcriber.whisper_transcriber import WhisperTranscriber
# Note: Using renamed implementation device_monitor.py (2025-02-24 standardization)
from audio_transcriber.device_monitor import WASAPIMonitor

logger = logging.getLogger(__name__)

async def initialize_components(coordinator: MonitoringCoordinator):
    """Initialize system components with proper dependency management."""
    try:
        # Initialize AlertConfig with reasonable thresholds
        config = AlertConfig(
            cpu_threshold=80.0,  # 80% CPU usage threshold
            memory_threshold=1024.0,  # 1GB memory threshold
            storage_latency_threshold=0.5,  # 500ms storage write latency threshold
            buffer_threshold=90.0  # 90% buffer usage threshold
        )
        config.validate()

        # Initialize core monitoring and alert system first
        alert_system = AlertSystem(config=config, coordinator=coordinator)
        coordinator.alert_system = alert_system

        # Initialize components with coordinator integration
        storage_manager = StorageManager(base_path=project_root / "recordings")
        await storage_manager.initialize()  # Initialize storage first
        
        # Initialize WhisperTranscriber in mock mode for development
        # Note: API key will be set through application settings in production
        whisper_transcriber = WhisperTranscriber(
            api_key="mock_key",  # Mock key for development
            coordinator=coordinator,
            max_retries=3,
            rate_limit_per_min=50
        )
        
        buffer_manager = BufferManager(coordinator=coordinator)
        await coordinator.register_component(buffer_manager, "buffer_manager")
        
        # Resolve circular dependency through coordinator
        coordinator.set_audio_queue(buffer_manager.get_processing_queue("left"))
        
        wasapi_monitor = WASAPIMonitor(coordinator)
        await coordinator.register_component(wasapi_monitor, "wasapi_monitor")
        
        audio_capture = AdaptiveAudioCapture(coordinator)
        await coordinator.register_component(audio_capture, "audio_capture")
        
        # Already initialized above with mock key
        await coordinator.register_component(whisper_transcriber, "whisper_transcriber")
        
        signal_processor = SignalProcessor(
            coordinator=coordinator,
            transcriber=whisper_transcriber
        )
        await coordinator.register_component(signal_processor, "signal_processor")

        return {
            'alert_system': alert_system,
            'storage_manager': storage_manager,
            'buffer_manager': buffer_manager,
            'wasapi_monitor': wasapi_monitor,
            'audio_capture': audio_capture,
            'signal_processor': signal_processor
        }

    except Exception as e:
        logger.error(f"Component initialization failed: {e}")
        await coordinator.report_error("main", f"Initialization error: {e}")
        raise

async def cleanup_components(components: dict, coordinator: MonitoringCoordinator):
    """Clean up components in reverse initialization order."""
    try:
        # Follow lock hierarchy during cleanup
        async with coordinator.component_lock("main"):
            for name, component in reversed(list(components.items())):
                try:
                    if hasattr(component, 'cleanup'):
                        await component.cleanup()
                    await coordinator.unregister_component(name)
                except Exception as e:
                    logger.error(f"Error cleaning up {name}: {e}")
                    await coordinator.report_error("main", f"Cleanup error in {name}: {e}")
    except Exception as e:
        logger.error(f"Component cleanup failed: {e}")
        await coordinator.report_error("main", f"Cleanup error: {e}")
        raise

async def main_async():
    """Asynchronous main entry point with proper resource management."""
    coordinator = None
    components = None
    
    try:
        # Set working directory to project root
        os.chdir(project_root)
        logger.info(f"Current working directory: {os.getcwd()}")

        # Initialize coordinator first
        coordinator = MonitoringCoordinator()
        await coordinator.initialize()

        # Initialize components
        components = await initialize_components(coordinator)

        # Create and configure main window
        app = QApplication(sys.argv)
        main_window = MainWindow(
            coordinator,
            components['audio_capture'],
            components['buffer_manager'],
            components['signal_processor'],
            components['storage_manager']
        )

        # Set up monitoring timer with coordinator integration
        main_window.monitoring_timer = QTimer(main_window)
        main_window.monitoring_timer.timeout.connect(main_window.update_monitoring)
        main_window.monitoring_timer.start(1000)  # Update every second

        # Start components
        await components['audio_capture'].start_capture()
        await coordinator.start_monitoring()

        main_window.show()
        return app.exec()

    except Exception as e:
        logger.error(f"Error in main: {e}")
        if coordinator:
            await coordinator.report_error("main", f"Fatal error: {e}")
        return 1

    finally:
        if components and coordinator:
            await cleanup_components(components, coordinator)
        if coordinator:
            await coordinator.cleanup()

def main():
    """Synchronous entry point that runs the async main."""
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(main_async())
    
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        return 1
    
    finally:
        loop.close()

if __name__ == "__main__":
    sys.exit(main())
