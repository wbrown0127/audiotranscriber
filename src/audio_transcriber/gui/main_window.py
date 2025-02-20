from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QSystemTrayIcon,
    QMenu, QApplication, QStyle
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QAction
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.buffer_manager import BufferManager
from audio_transcriber.storage_manager import StorageManager

class MainWindow(QMainWindow):
    """Main application window."""

    # Signals for inter-component communication
    audio_state_changed = Signal(bool)  # True for recording, False for stopped
    processing_progress = Signal(float)  # 0-100 progress value
    error_occurred = Signal(str)  # Error message

    def __init__(self, monitoring_coordinator: MonitoringCoordinator, audio_capture: AdaptiveAudioCapture, buffer_manager: BufferManager, signal_processor: StorageManager, storage_manager: StorageManager):
        super().__init__()
        self.setWindowTitle("Audio Transcriber")

        # Use passed components
        self.monitoring_coordinator = monitoring_coordinator
        self.audio_capture = audio_capture
        self.buffer_manager = buffer_manager
        self.signal_processor = signal_processor
        self.storage_manager = storage_manager
        
        self.setup_ui()
        self.setup_tray()
        self.setup_connections()

    def setup_ui(self):
        """Initialize the user interface components."""
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Status section
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.cpu_label = QLabel("CPU: 0%")
        self.memory_label = QLabel("Memory: 0 MB")
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.cpu_label)
        status_layout.addWidget(self.memory_label)
        layout.addLayout(status_layout)

        # Detailed metrics section
        metrics_layout = QHBoxLayout()
        self.buffer_label = QLabel("Buffer: 0%")
        self.io_label = QLabel("Storage Latency: 0.000 s")
        self.error_count_label = QLabel("Errors: 0")
        metrics_layout.addWidget(self.buffer_label)
        metrics_layout.addWidget(self.io_label)
        metrics_layout.addWidget(self.error_count_label)
        layout.addLayout(metrics_layout)
        
        # Progress section
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_label = QLabel("No active transcription")
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)
        
        # Control buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Recording")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)
        
        # Error display
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

    def setup_tray(self):
        """Initialize system tray icon and menu."""
        # Use a system standard icon
        icon = QApplication.style().standardIcon(QStyle.SP_MediaPlay)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_menu = QMenu()
        
        # Tray menu actions
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show)
        
        toggle_action = QAction("Start Recording", self)
        toggle_action.triggered.connect(self.toggle_recording)
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        
        # Add actions to tray menu
        self.tray_menu.addAction(show_action)
        self.tray_menu.addAction(toggle_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

    def setup_connections(self):
        """Connect signals and slots."""
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)

        # Connect custom signals
        self.audio_state_changed.connect(self.update_recording_state)
        self.processing_progress.connect(self.update_progress)
        self.error_occurred.connect(self.show_error)

        # Connect to MonitoringCoordinator and AlertSystem
        self.monitoring_coordinator.alert_system.alert_triggered.connect(
            lambda title, msg, level: self.handle_alert(title, msg, level)
        )

    @Slot()
    def start_recording(self):
        """Start audio recording and transcription."""
        try:
            # Start audio capture
            self.audio_capture.start_capture()

            # Update UI
            self.audio_state_changed.emit(True)
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_label.setText("Recording...")
            self.error_label.hide()

            # Update tray icon to stop icon
            self.tray_icon.setIcon(
                QApplication.style().standardIcon(QStyle.SP_MediaStop)
            )

            # Start progress updates
            self.progress_timer = QTimer(self)
            self.progress_timer.timeout.connect(
                self.update_transcription_progress
            )
            self.progress_timer.start(500)  # Update every 500ms
        except Exception as e:
            self.error_occurred.emit(str(e))

    @Slot()
    def stop_recording(self):
        """Stop audio recording and transcription."""
        try:
            # Stop audio capture
            self.audio_capture.stop_capture()

            # Update UI
            self.audio_state_changed.emit(False)
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.status_label.setText("Ready")

            # Update tray icon to play icon
            self.tray_icon.setIcon(
                QApplication.style().standardIcon(QStyle.SP_MediaPlay)
            )

            # Stop progress updates
            if hasattr(self, "progress_timer"):
                self.progress_timer.stop()
        except Exception as e:
            self.error_occurred.emit(str(e))

    @Slot()
    def toggle_recording(self):
        """Toggle recording state from tray icon."""
        if self.start_button.isEnabled():
            self.start_recording()
        else:
            self.stop_recording()

    @Slot(bool)
    def update_recording_state(self, is_recording):
        """Update UI elements based on recording state."""
        self.start_button.setEnabled(not is_recording)
        self.stop_button.setEnabled(is_recording)
        status = "Recording..." if is_recording else "Ready"
        self.status_label.setText(status)

    @Slot(float)
    def update_progress(self, value):
        """Update progress bar and label."""
        self.progress_bar.setValue(int(value))
        self.progress_label.setText(f"Processing: {value:.1f}%")

    @Slot(str)
    def show_error(self, message):
        """Display error message in UI."""
        self.error_label.setText(f"Error: {message}")
        self.error_label.show()

    @Slot(str, str, int)
    def handle_alert(self, title, message, level):
        """Handle alert triggered by AlertSystem."""
        # Display alert in UI
        self.error_label.setText(f"Alert ({title}): {message}")
        self.error_label.show()

        # Log the alert (using print for now, can be replaced with proper logging)
        print(f"ALERT: [{level}] {title} - {message}")

        # Optionally pause recording based on alert level
        if level >= 2:  # Critical or higher
            if self.stop_button.isEnabled():  # if recording
                self.stop_recording()
                self.status_label.setText(
                    "Recording paused due to critical alert."
                )

    def closeEvent(self, event):
        """Handle window close event."""
        # Minimize to tray instead of closing
        event.ignore()
        self.hide()

    @Slot()
    def update_monitoring(self):
        """Update performance monitoring displays."""
        try:
            # Get system state from monitoring coordinator
            system_state = self.monitoring_coordinator.get_state()
            config = self.monitoring_coordinator.alert_system.config # Get AlertConfig

            # Update CPU usage
            cpu_usage = system_state.cpu_usage
            self.cpu_label.setText(f"CPU: {cpu_usage:.1f}%")
            if cpu_usage > config.cpu_threshold:
                self.cpu_label.setStyleSheet("color: red;")
            else:
                self.cpu_label.setStyleSheet("")

            # Update memory usage
            memory_usage = system_state.memory_usage
            self.memory_label.setText(f"Memory: {memory_usage:.1f} MB")
            if memory_usage > config.memory_threshold:
                self.memory_label.setStyleSheet("color: red;")
            else:
                self.memory_label.setStyleSheet("")

            # Update buffer label
            buffer_size = system_state.buffer_size
            max_buffer_size = self.buffer_manager.processing_queue.maxsize
            buffer_percentage = (
                (buffer_size / max_buffer_size) * 100
                if max_buffer_size > 0
                else 0
            )
            self.buffer_label.setText(f"Buffer: {buffer_percentage:.1f}%")

            if buffer_percentage > config.buffer_health_threshold:
                self.buffer_label.setStyleSheet("color: red;")
            elif buffer_percentage > (config.buffer_health_threshold * 0.75):
                self.buffer_label.setStyleSheet("color: orange;")
            else:
                self.buffer_label.setStyleSheet("")

            # Update I/O label (using storage latency)
            write_speed = system_state.storage_latency
            self.io_label.setText(f"Storage Latency: {write_speed:.3f} s")
            if write_speed > config.storage_latency_threshold:
                self.io_label.setStyleSheet("color: orange;")
            else:
                self.io_label.setStyleSheet("")

            # Update error count label
            error_count = system_state.error_count
            self.error_count_label.setText(f"Errors: {error_count}")
            if error_count > 0:
                self.error_count_label.setStyleSheet("color: red;")
            else:
                self.error_count_label.setStyleSheet("")

            # Update status with any warnings
            status_messages = []
            if not system_state.stream_health:
                status_messages.append("Audio stream unstable")
            if system_state.storage_latency > config.storage_latency_threshold:
                status_messages.append("High storage latency")

            if status_messages:
                self.status_label.setText(" | ".join(status_messages))
                self.status_label.setStyleSheet("color: orange;")
            elif not self.stop_button.isEnabled():  # Not recording
                self.status_label.setText("Ready")
                self.status_label.setStyleSheet("")

        except Exception as e:
            self.error_occurred.emit(f"Monitoring error: {str(e)}")

    @Slot()
    @Slot(dict)
    def update_performance_data(self, stats: dict):
        """Update performance data displays based on monitoring stats."""
        try:
            # Update CPU and memory usage if available
            if "cpu_usage" in stats:
                self.cpu_label.setText(f"CPU: {stats['cpu_usage']:.1f}%")
            if "memory_usage" in stats:
                self.memory_label.setText(f"Memory: {stats['memory_usage']:.1f} MB")
            
            # Update buffer metrics if available
            if "buffer_usage" in stats:
                self.buffer_label.setText(f"Buffer: {stats['buffer_usage']:.1f}%")
            
            # Update I/O metrics if available
            if "storage_latency" in stats:
                self.io_label.setText(f"Storage Latency: {stats['storage_latency']:.3f} s")
            
            # Update error count if available
            if "error_count" in stats:
                self.error_count_label.setText(f"Errors: {stats['error_count']}")
                
        except Exception as e:
            self.error_occurred.emit(f"Performance data update error: {str(e)}")

    def update_transcription_progress(self):
        """Update transcription progress based on signal processor status."""
        try:
            status = self.signal_processor.get_status()  # Get status
            if "progress" in status:
                self.processing_progress.emit(status["progress"])

            # Update progress label with additional info
            if "current_file" in status:
                self.progress_label.setText(
                    f"Processing: {status['progress']:.1f}% | File: {status['current_file']}"
                )
        except Exception as e:
            self.error_occurred.emit(f"Progress update error: {str(e)}")
        if hasattr(self, "progress_timer"):
            self.progress_timer.stop()
