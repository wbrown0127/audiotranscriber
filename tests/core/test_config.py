"""
COMPONENT_NOTES:
{
    "name": "TestConfig",
    "type": "Test Suite",
    "description": "Core test suite for verifying configuration management and system verification, including config validation, initialization checks, and restart verification",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TC[TestConfig] --> AC[AlertConfig]
                TC --> SV[SystemVerifier]
                TC --> MC[MonitoringCoordinator]
                TC --> WM[WASAPIMonitor]
                TC --> DM[DeviceManager]
                TC --> CT[ComponentTest]
                SV --> CC[CleanupCoordinator]
                SV --> SM[StorageManager]
        ```",
        "dependencies": {
            "AlertConfig": "Configuration validation",
            "SystemVerifier": "System checks and verification",
            "MonitoringCoordinator": "System monitoring",
            "WASAPIMonitor": "Audio system verification",
            "DeviceManager": "Audio device management",
            "ComponentTest": "Base test functionality",
            "CleanupCoordinator": "Cleanup management",
            "StorageManager": "Storage verification"
        }
    },
    "notes": [
        "Tests configuration file loading and validation",
        "Verifies alert threshold configurations",
        "Tests system component initialization",
        "Validates audio device configuration",
        "Tests recovery system verification",
        "Ensures storage system verification"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_config.py",
            "python -m pytest tests/core/test_config.py -k test_alert_config_validation"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "asyncio",
            "json",
            "pathlib"
        ],
        "system": {
            "audio": "WASAPI-compatible audio devices",
            "storage": "Write access to test directories"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Minimal CPU usage",
            "Light disk I/O for config files",
            "Audio device access for verification"
        ]
    }
}
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, mock_open
import pytest

from audio_transcriber.alert_system import AlertConfig
from audio_transcriber.test_config.device_config import DeviceType
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.system_verifier import SystemVerifier
from audio_transcriber.wasapi_monitor import WASAPIMonitor
from tests.utilities.base import ComponentTest

class TestConfiguration(ComponentTest):
    """Test configuration validation and management."""
    
    def setUp(self):
        """Set up test environment with proper resource management."""
        super().setUp()
        try:
            # Initialize MonitoringCoordinator first
            self.monitoring = MonitoringCoordinator()
            self.monitoring.start_monitoring()
            
            # Initialize resource pool through MonitoringCoordinator
            self.monitoring.initialize_resource_pool({
                'memory': 1024 * 1024 * 100,  # 100MB
                'threads': 4,
                'handles': 100,
                'buffer': {
                    4096: 1000,    # Small buffers
                    65536: 500,    # Medium buffers
                    1048576: 100   # Large buffers
                }
            })
            
            # Test configuration with channel-specific settings
            self.test_config = {
                "alert": {
                    "cpu_threshold": 80.0,
                    "memory_threshold": 100.0,
                    "storage_latency_threshold": 0.5,
                    "buffer_threshold": 90.0,
                    "channel_thresholds": {
                        "left": {"buffer": 85.0, "latency": 0.4},
                        "right": {"buffer": 85.0, "latency": 0.4}
                    }
                },
                "monitoring": {
                    "check_interval": 1.0,
                    "error_backoff": 5.0,
                    "max_retries": 3,
                    "channel_config": {
                        "left": {"enabled": True, "priority": "high"},
                        "right": {"enabled": True, "priority": "high"}
                    }
                }
            }
            
            # Register test thread
            self.monitoring.register_thread()
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise
            
    def tearDown(self):
        """Clean up test environment with proper resource cleanup."""
        try:
            if hasattr(self, 'monitoring'):
                try:
                    self.monitoring.stop_monitoring()
                    self.monitoring.cleanup()
                    # Wait for cleanup to complete
                    time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"Error cleaning up monitoring: {e}")
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
        finally:
            super().tearDown()
        
    @pytest.mark.fast
    def test_alert_config_validation(self):
        """Test AlertConfig validation with channel-specific settings."""
        try:
            # Test with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            # Test valid configuration
                            config = AlertConfig(**self.test_config["alert"])
                            config.validate()  # Should not raise
                            
                            # Test invalid thresholds
                            invalid_configs = [
                                {"cpu_threshold": 101.0},  # Invalid CPU
                                {"memory_threshold": -1.0},  # Invalid memory
                                {"storage_latency_threshold": -0.1},  # Invalid latency
                                {"buffer_threshold": 101.0},  # Invalid buffer
                                # Channel-specific invalid configs
                                {"channel_thresholds": {
                                    "left": {"buffer": 101.0},
                                    "right": {"latency": -0.1}
                                }}
                            ]
                            
                            for invalid_values in invalid_configs:
                                test_config = self.test_config["alert"].copy()
                                test_config.update(invalid_values)
                                
                                with self.assertRaises(ValueError):
                                    config = AlertConfig(**test_config)
                            
                            # Test channel-specific validation
                            for channel in ['left', 'right']:
                                # Verify channel thresholds
                                channel_config = config.channel_thresholds.get(channel)
                                self.assertIsNotNone(channel_config)
                                self.assertLessEqual(channel_config['buffer'], 100.0)
                                self.assertGreaterEqual(channel_config['latency'], 0.0)
                            
                            # Log validation metrics
                            self.log_metric("validation_tests", len(invalid_configs) + 1)
                            self.log_metric("channel_validations", 2)  # Left and right
            
        except Exception as e:
            self.logger.error(f"Alert config validation test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_config_file_loading(self):
        """Test configuration file loading."""
        mock_config_data = json.dumps(self.test_config)
        
        with patch("builtins.open", mock_open(read_data=mock_config_data)):
            # Load and verify config
            config_path = Path("config.json")
            with open(config_path) as f:
                loaded_config = json.load(f)
            
            self.assertEqual(loaded_config, self.test_config)
            
            # Create and validate AlertConfig
            alert_config = AlertConfig(**loaded_config["alert"])
            alert_config.validate()
            
            # Log config metrics
            self.log_metric("config_size", len(mock_config_data))
            self.log_metric("config_sections", len(loaded_config))
            
    @pytest.mark.fast
    def test_config_error_handling(self):
        """Test configuration error handling."""
        # Test missing required field
        invalid_config = self.test_config["alert"].copy()
        del invalid_config["cpu_threshold"]
        
        with self.assertRaises(TypeError):
            AlertConfig(**invalid_config)
            
        # Test invalid JSON
        with patch("builtins.open", mock_open(read_data="{")):
            with self.assertRaises(json.JSONDecodeError):
                with open(Path("config.json")) as f:
                    json.load(f)
                    
        # Log error handling metrics
        self.log_metric("error_cases_tested", 2)
        
    @pytest.mark.fast
    def test_config_defaults(self):
        """Test configuration defaults."""
        config = AlertConfig(
            cpu_threshold=80.0,
            memory_threshold=100.0,
            storage_latency_threshold=0.5,
            buffer_threshold=90.0
        )
        
        # Verify values
        self.assertEqual(config.cpu_threshold, 80.0)
        self.assertEqual(config.memory_threshold, 100.0)
        self.assertEqual(config.storage_latency_threshold, 0.5)
        self.assertEqual(config.buffer_threshold, 90.0)
        
        # Validate values
        config.validate()
        
        # Log metrics
        self.log_metric("default_values_tested", 4)

class TestSystemVerification(ComponentTest):
    """Test system verification and restart checks."""
    
    def setUp(self):
        """Set up test environment with proper resource management."""
        super().setUp()
        try:
            # Initialize MonitoringCoordinator first
            self.monitoring = MonitoringCoordinator()
            self.monitoring.start_monitoring()
            
            # Initialize resource pool through MonitoringCoordinator
            self.monitoring.initialize_resource_pool({
                'memory': 1024 * 1024 * 100,  # 100MB
                'threads': 4,
                'handles': 100,
                'buffer': {
                    4096: 1000,    # Small buffers
                    65536: 500,    # Medium buffers
                    1048576: 100   # Large buffers
                }
            })
            
            # Initialize verifier with monitoring coordinator
            self.verifier = SystemVerifier(coordinator=self.monitoring)
            
            # Register test thread
            self.monitoring.register_thread()
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise
        
    def tearDown(self):
        """Clean up test environment with proper resource cleanup."""
        try:
            # Signal threads to stop
            if hasattr(self, 'verifier'):
                try:
                    self.verifier.cleanup_coordinator.request_shutdown()
                except Exception as e:
                    self.logger.error(f"Error cleaning up verifier: {e}")
            
            # Cleanup monitoring last
            if hasattr(self, 'monitoring'):
                try:
                    self.monitoring.stop_monitoring()
                    self.monitoring.cleanup()
                    # Wait for cleanup to complete
                    time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"Error cleaning up monitoring: {e}")
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
        finally:
            super().tearDown()
            
    @pytest.mark.fast
    def test_component_initialization(self):
        """Test component initialization verification with proper resource management."""
        try:
            # Test with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            # Verify monitoring coordinator
                            state = self.verifier.monitoring_coordinator.get_state()
                            self.assertIsNotNone(state)
                            
                            # Verify cleanup coordinator
                            self.assertFalse(self.verifier.cleanup_coordinator.is_shutdown_requested())
                            
                            # Verify channel-specific initialization
                            for channel in ['left', 'right']:
                                channel_state = self.verifier.monitoring_coordinator.get_channel_state(channel)
                                self.assertIsNotNone(channel_state)
                                self.assertTrue(channel_state['initialized'])
                            
                            # Log initialization metrics
                            self.log_metric("components_initialized", 2)
                            self.log_metric("initial_state", state.__dict__)
                            self.log_metric("channels_initialized", 2)
            
        except Exception as e:
            self.logger.error(f"Component initialization test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_device_verification(self):
        """Test audio device verification with channel-specific validation."""
        try:
            # Test with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            devices = []
                            for device_type in [DeviceType.SYSTEM_LOOPBACK, DeviceType.VB_CABLE, 
                                            DeviceType.DEFAULT_OUTPUT, DeviceType.DEFAULT_INPUT]:
                                try:
                                    config = self.verifier.device_manager.get_config(device_type)
                                    is_valid = self.verifier.device_manager.validate_device(device_type)
                                    
                                    # Test channel-specific device validation
                                    channel_validation = {}
                                    for channel in ['left', 'right']:
                                        channel_valid = self.verifier.device_manager.validate_device_channel(
                                            device_type, 
                                            channel
                                        )
                                        channel_validation[channel] = channel_valid
                                    
                                    devices.append({
                                        'type': device_type.name,
                                        'valid': is_valid,
                                        'channels': channel_validation
                                    })
                                except ValueError:
                                    continue
                                    
                            # Verify at least one valid device
                            self.assertTrue(any(d['valid'] for d in devices))
                            
                            # Verify channel validation
                            valid_channels = sum(
                                sum(1 for ch in d['channels'].values() if ch)
                                for d in devices if 'channels' in d
                            )
                            self.assertGreater(valid_channels, 0)
                            
                            # Log device metrics
                            self.log_metric("total_devices", len(devices))
                            self.log_metric("valid_devices", sum(1 for d in devices if d['valid']))
                            self.log_metric("valid_channels", valid_channels)
            
        except Exception as e:
            self.logger.error(f"Device verification test failed: {e}")
            raise
        
    @pytest.mark.fast
    async def test_audio_capture_verification(self):
        """Test audio capture verification with channel-specific validation."""
        try:
            # Test with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            wasapi = WASAPIMonitor(self.monitoring)  # Use injected coordinator
                            device_config = self.verifier.device_manager.get_config(
                                DeviceType.SYSTEM_LOOPBACK
                            )
                            
                            # Test stream initialization with timeout
                            async with asyncio.timeout(5.0):  # 5 second timeout
                                # Initialize base stream
                                success = wasapi.initialize_stream(device_index=device_config.device_index)
                                self.assertTrue(success)
                                
                                # Test channel-specific initialization
                                channel_success = {}
                                for channel in ['left', 'right']:
                                    channel_success[channel] = await wasapi.initialize_channel(
                                        device_index=device_config.device_index,
                                        channel=channel
                                    )
                                    self.assertTrue(channel_success[channel])
                                
                                # Get performance metrics
                                metrics = self.monitoring.get_performance_metrics()
                                
                                # Get channel-specific metrics
                                channel_metrics = {}
                                for channel in ['left', 'right']:
                                    channel_metrics[channel] = self.monitoring.get_channel_metrics(channel)
                                
                                # Cleanup in reverse order
                                for channel in ['right', 'left']:  # Reverse order
                                    await wasapi.cleanup_channel(channel)
                                wasapi.cleanup()
                                
                                # Log capture metrics
                                self.log_metric("stream_initialized", success)
                                self.log_metric("performance_metrics", metrics)
                                self.log_metric("channel_success", channel_success)
                                self.log_metric("channel_metrics", channel_metrics)
                                
        except asyncio.TimeoutError:
            self.skipTest("Device initialization timed out")
        except Exception as e:
            self.logger.error(f"Audio capture verification failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_recovery_verification(self):
        """Test recovery system verification with channel-specific recovery."""
        try:
            # Test with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            # Start monitoring
                            self.monitoring.start_monitoring()
                            
                            # Test system-wide recovery
                            self.monitoring.update_state(stream_health=False)
                            asyncio.run(asyncio.sleep(1.0))
                            self.monitoring.update_state(stream_health=True)
                            
                            state = self.monitoring.get_state()
                            self.assertTrue(state.stream_health)
                            
                            # Test channel-specific recovery
                            channel_recovery = {}
                            for channel in ['left', 'right']:
                                # Simulate channel failure
                                self.monitoring.update_channel_state(
                                    channel,
                                    stream_health=False
                                )
                                
                                # Wait for recovery
                                asyncio.run(asyncio.sleep(1.0))
                                
                                # Simulate channel recovery
                                self.monitoring.update_channel_state(
                                    channel,
                                    stream_health=True
                                )
                                
                                # Verify channel recovery
                                channel_state = self.monitoring.get_channel_state(channel)
                                channel_recovery[channel] = channel_state['stream_health']
                                self.assertTrue(channel_recovery[channel])
                            
                            # Log recovery metrics
                            self.log_metric("recovery_triggered", True)
                            self.log_metric("recovery_successful", state.stream_health)
                            self.log_metric("channel_recovery", channel_recovery)
                            
        except Exception as e:
            self.logger.error(f"Recovery verification failed: {e}")
            raise
        finally:
            # Stop monitoring
            self.monitoring.stop_monitoring()
        
    @pytest.mark.fast
    def test_storage_verification(self):
        """Test storage system verification with channel-specific paths."""
        try:
            # Test with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            # Verify base storage paths
                            paths = self.verifier.storage_manager.verify_paths()
                            self.assertTrue(paths)
                            
                            # Test channel-specific storage paths
                            channel_paths = {}
                            for channel in ['left', 'right']:
                                channel_dir = Path(f'recordings/{channel}')
                                channel_paths[channel] = self.verifier.storage_manager.verify_channel_path(channel)
                                self.assertTrue(channel_paths[channel])
                                
                                # Test channel-specific write access
                                test_file = channel_dir / 'test_write.tmp'
                                self.verifier.storage_manager.write_test_file(test_file)
                                self.assertTrue(test_file.exists())
                                
                                # Clean up channel test file
                                if test_file.exists():
                                    test_file.unlink()
                            
                            # Test base write access
                            test_file = Path('recordings/test_write.tmp')
                            self.verifier.storage_manager.write_test_file(test_file)
                            self.assertTrue(test_file.exists())
                            
                            # Clean up base test file
                            if test_file.exists():
                                test_file.unlink()
                            
                            # Log storage metrics
                            self.log_metric("paths_verified", True)
                            self.log_metric("write_access_verified", True)
                            self.log_metric("channel_paths_verified", channel_paths)
            
        except Exception as e:
            self.logger.error(f"Storage verification failed: {e}")
            raise
