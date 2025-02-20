import sys
import asyncio
import signal
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from .main_window import MainWindow

class AsyncApplication(QApplication):
    """QApplication with async event loop integration."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set up async loop
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Create timer for async tasks
        self.async_timer = QTimer()
        self.async_timer.timeout.connect(self._process_async_tasks)
        self.async_timer.start(10)  # 10ms interval
        
        # Handle interrupts gracefully
        signal.signal(signal.SIGINT, self._handle_interrupt)
        
    def _process_async_tasks(self):
        """Process pending async tasks."""
        self.loop.stop()
        self.loop.run_forever()
        
    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signal."""
        self.quit()
        
    def exec(self):
        """Run the application."""
        try:
            return super().exec()
        finally:
            # Clean up async resources
            self.async_timer.stop()
            pending = asyncio.all_tasks(self.loop)
            self.loop.run_until_complete(asyncio.gather(*pending))
            self.loop.close()

def run():
    """Initialize and run the GUI application."""
    # Enable Windows 11 style
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = AsyncApplication(sys.argv)
    app.setStyle('Windows')  # Use native Windows style
    
    # Set application metadata
    app.setApplicationName("Audio Transcriber")
    app.setApplicationVersion("0.4.1")  # Updated version
    app.setOrganizationName("Audio Transcriber")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Handle application shutdown
    app.aboutToQuit.connect(lambda: cleanup(window))
    
    return app.exec()

def cleanup(window):
    """Clean up application resources."""
    try:
        # Stop recording if active
        if window.stop_button.isEnabled():
            window.stop_recording()
        
        # Clean up components
        window.loop.run_until_complete(window.transcriber.cleanup())
        window.loop.run_until_complete(window.storage_manager.cleanup())
        
        # Stop timers
        window.monitor_timer.stop()
        if hasattr(window, 'progress_timer'):
            window.progress_timer.stop()
            
    except Exception as e:
        print(f"Cleanup error: {e}")  # Log but don't block shutdown
