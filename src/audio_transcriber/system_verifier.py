"""
COMPONENT_NOTES:
{
    "name": "SystemVerifier",
    "type": "Core Component",
    "description": "System verification utility that validates system initialization, component health, and recovery functionality after system restart",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                SV[SystemVerifier] --> MC[MonitoringCoordinator]
                SV --> WM[WASAPIMonitor]
                SV --> CC[CleanupCoordinator]
                SV --> RL[RecoveryLogger]
                SV --> SM[StateMachine]
                SV --> ST[StorageManager]
                SV --> DM[DeviceManager]
                MC --> PM[PerformanceMetrics]
                WM --> AD[AudioDevices]
                CC --> CS[CleanupState]
                RL --> LF[LogFiles]
                SM --> RS[RecoveryState]
                ST --> FS[FileSystem]
                DM --> DC[DeviceConfig]
        ```",
        "dependencies": {
            "MonitoringCoordinator": "System monitoring",
            "WASAPIMonitor": "Audio device management",
            "CleanupCoordinator": "Resource cleanup",
            "RecoveryLogger": "Recovery logging",
            "StateMachine": "State management",
            "StorageManager": "Storage operations",
            "DeviceManager": "Device configuration",
            "PerformanceMetrics": "System metrics",
            "AudioDevices": "Device access",
            "CleanupState": "Cleanup tracking",
            "LogFiles": "Log management",
            "RecoveryState": "Recovery tracking",
            "FileSystem": "Storage access",
            "DeviceConfig": "Device settings"
        }
    },
    "notes": [
        "Verifies component initialization",
        "Validates device availability",
        "Tests audio capture functionality",
        "Checks recovery system operation",
        "Validates storage system access",
        "Generates verification reports"
    ],
    "usage": {
        "examples": [
            "verifier = SystemVerifier()",
            "success = verifier.run_verification()",
            "results = verifier.results"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "json",
            "pathlib",
            "datetime"
        ],
        "system": {
            "audio": "WASAPI-compatible device",
            "storage": "Write access to logs"
        }
    },
    "performance": {
        "execution_time": "Completes within 5 seconds",
        "resource_usage": [
            "Minimal CPU usage",
            "Light memory footprint",
            "Brief audio device access",
            "Small disk I/O operations"
        ]
    }
}
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .monitoring_coordinator import MonitoringCoordinator
# Note: Using renamed implementation device_monitor.py (2025-02-24 standardization)
from .device_monitor import WASAPIMonitor
from .cleanup_coordinator import CleanupCoordinator
from .recovery_logger import RecoveryLogger
from .state_machine import StateMachine
from .storage_manager import StorageManager
from .test_config.device_config import DeviceManager, DeviceType

class SystemVerifier:
    """Verifies system state and functionality after restart."""

    def __init__(self):
        """Initialize system components for verification."""
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {},
            'overall_status': 'pending'
        }
        
        # Initialize components in order
        self.device_manager = DeviceManager()
        self.monitoring_coordinator = MonitoringCoordinator()
        self.state_machine = StateMachine()
        self.storage_manager = StorageManager("recordings")  # Base path for recordings
        self.cleanup_coordinator = CleanupCoordinator(self.monitoring_coordinator)
        self.recovery_logger = RecoveryLogger("logs")

    def run_verification(self) -> bool:
        """Run all verification checks."""
        try:
            # Start core services
            self.monitoring_coordinator.start_monitoring()
            self.cleanup_coordinator.start()
            
            # Run verification tests
            self._verify_component_initialization()
            self._verify_device_availability()
            self._verify_audio_capture()
            self._verify_recovery_system()
            self._verify_storage_system()
            
            # Calculate overall status
            failed_tests = [
                test for test, result in self.results['tests'].items()
                if result['status'] == 'failed'
            ]
            
            self.results['overall_status'] = (
                'failed' if failed_tests else 'passed'
            )
            
            return len(failed_tests) == 0
            
        except Exception as e:
            self.results['error'] = str(e)
            self.results['overall_status'] = 'error'
            return False
            
        finally:
            # Clean up
            self.cleanup_coordinator.request_shutdown()
            self.monitoring_coordinator.stop_monitoring()
            self.device_manager.cleanup()
            
            # Save results
            self._save_results()

    def _verify_component_initialization(self):
        """Verify all components initialize properly."""
        test_name = 'component_initialization'
        try:
            # Verify monitoring coordinator
            state = self.monitoring_coordinator.get_state()
            self.results['tests'][test_name] = {
                'status': 'passed',
                'details': {
                    'monitoring_active': True,
                    'initial_state': state.__dict__
                }
            }
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'failed',
                'error': str(e)
            }

    def _verify_device_availability(self):
        """Verify required audio devices are available."""
        test_name = 'device_availability'
        try:
            devices = []
            for device_type in DeviceType:
                try:
                    config = self.device_manager.get_config(device_type)
                    is_valid = self.device_manager.validate_device(device_type)
                    devices.append({
                        'type': device_type.name,
                        'name': config.name,
                        'valid': is_valid
                    })
                except ValueError:
                    continue
            
            # At least one device should be available
            if not any(d['valid'] for d in devices):
                raise RuntimeError("No valid audio devices found")
            
            self.results['tests'][test_name] = {
                'status': 'passed',
                'details': {'devices': devices}
            }
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'failed',
                'error': str(e)
            }

    def _verify_audio_capture(self):
        """Verify audio capture functionality."""
        test_name = 'audio_capture'
        try:
            wasapi = WASAPIMonitor(self.monitoring_coordinator)
            device_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
            
            # Initialize stream
            success = wasapi.initialize_stream(
                device_index=device_config.device_index
            )
            if not success:
                raise RuntimeError("Failed to initialize audio stream")
            
            # Let it run briefly
            time.sleep(1.0)
            
            # Get performance metrics
            metrics = self.monitoring_coordinator.get_performance_metrics()
            
            wasapi.cleanup()
            
            self.results['tests'][test_name] = {
                'status': 'passed',
                'details': {
                    'stream_initialized': True,
                    'metrics': metrics
                }
            }
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'failed',
                'error': str(e)
            }

    def _verify_recovery_system(self):
        """Verify recovery system functionality."""
        test_name = 'recovery_system'
        try:
            wasapi = WASAPIMonitor(self.monitoring_coordinator)
            device_config = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
            
            # Initialize stream
            success = wasapi.initialize_stream(
                device_index=device_config.device_index
            )
            if not success:
                raise RuntimeError("Failed to initialize audio stream")
            
            # Trigger recovery
            self.monitoring_coordinator.update_state(stream_health=False)
            time.sleep(1.0)
            
            # Verify recovery
            state = self.monitoring_coordinator.get_state()
            if not state.stream_health:
                raise RuntimeError("Failed to recover stream health")
            
            wasapi.cleanup()
            
            self.results['tests'][test_name] = {
                'status': 'passed',
                'details': {
                    'recovery_triggered': True,
                    'recovery_successful': True
                }
            }
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'failed',
                'error': str(e)
            }

    def _verify_storage_system(self):
        """Verify storage system functionality."""
        test_name = 'storage_system'
        try:
            # Verify storage paths
            paths = self.storage_manager.verify_paths()
            
            # Verify write access
            test_file = Path('recordings/test_write.tmp')
            self.storage_manager.write_test_file(test_file)
            
            # Clean up test file
            if test_file.exists():
                test_file.unlink()
            
            self.results['tests'][test_name] = {
                'status': 'passed',
                'details': {
                    'paths_verified': True,
                    'write_access': True
                }
            }
        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'failed',
                'error': str(e)
            }

    def _save_results(self):
        """Save verification results to file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_file = Path(f'tests/results/restart_verify_{timestamp}.json')
        result_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(result_file, 'w') as f:
            json.dump(self.results, f, indent=2)
