#!/usr/bin/env python3
import unittest
import json
from pathlib import Path
from unittest.mock import patch, mock_open

from audio_transcriber.alert_system import AlertConfig
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator


class TestConfiguration(unittest.IsolatedAsyncioTestCase):
    """Test suite for configuration management."""

    async def asyncSetUp(self):
        """Set up test fixtures before each test method."""
        self.test_config = {
            "alert": {
                "cpu_threshold": 80.0,
                "memory_threshold": 100.0,
                "storage_latency_threshold": 0.5,
                "buffer_threshold": 90.0
            },
            "monitoring": {
                "check_interval": 1.0,
                "error_backoff": 5.0,
                "max_retries": 3
            }
        }

    async def test_alert_config_validation(self):
        """Test AlertConfig validation."""
        # Test valid configuration
        config = AlertConfig(**self.test_config["alert"])
        config.validate()  # Should not raise

        # Test invalid CPU threshold
        with self.assertRaises(AssertionError):
            invalid_config = AlertConfig(
                cpu_threshold=101.0,
                memory_threshold=100.0,
                storage_latency_threshold=0.5,
                buffer_threshold=90.0
            )
            invalid_config.validate()

        # Test invalid memory threshold
        with self.assertRaises(AssertionError):
            invalid_config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold=-1.0,
                storage_latency_threshold=0.5,
                buffer_threshold=90.0
            )
            invalid_config.validate()

        # Test invalid storage latency threshold
        with self.assertRaises(AssertionError):
            invalid_config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold=100.0,
                storage_latency_threshold=-0.1,
                buffer_threshold=90.0
            )
            invalid_config.validate()

        # Test invalid buffer threshold
        with self.assertRaises(AssertionError):
            invalid_config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold=100.0,
                storage_latency_threshold=0.5,
                buffer_threshold=101.0
            )
            invalid_config.validate()

    async def test_config_file_loading(self):
        """Test loading configuration from file."""
        mock_config_data = json.dumps(self.test_config)
        
        with patch("builtins.open", mock_open(read_data=mock_config_data)):
            # Load config from file
            config_path = Path("config.json")
            with open(config_path) as f:
                loaded_config = json.load(f)
            
            # Verify loaded configuration matches test configuration
            self.assertEqual(loaded_config, self.test_config)
            
            # Create AlertConfig from loaded data
            alert_config = AlertConfig(**loaded_config["alert"])
            alert_config.validate()  # Should not raise
            
            # Verify values
            self.assertEqual(alert_config.cpu_threshold, 80.0)
            self.assertEqual(alert_config.memory_threshold, 100.0)
            self.assertEqual(alert_config.storage_latency_threshold, 0.5)
            self.assertEqual(alert_config.buffer_threshold, 90.0)

    async def test_config_error_handling(self):
        """Test configuration error handling."""
        # Test missing required field
        invalid_config = self.test_config["alert"].copy()
        del invalid_config["cpu_threshold"]
        
        with self.assertRaises(TypeError):
            AlertConfig(**invalid_config)

        # Test invalid JSON
        invalid_json = "{"  # Invalid JSON string
        with patch("builtins.open", mock_open(read_data=invalid_json)):
            with self.assertRaises(json.JSONDecodeError):
                config_path = Path("config.json")
                with open(config_path) as f:
                    json.load(f)

    async def test_config_type_validation(self):
        """Test configuration type validation."""
        # Test invalid type for CPU threshold
        with self.assertRaises(AssertionError):
            config = AlertConfig(
                cpu_threshold="80",  # String instead of float
                memory_threshold=100.0,
                storage_latency_threshold=0.5,
                buffer_threshold=90.0
            )
            config.validate()

        # Test invalid type for memory threshold
        with self.assertRaises(AssertionError):
            config = AlertConfig(
                cpu_threshold=80.0,
                memory_threshold="100",  # String instead of float
                storage_latency_threshold=0.5,
                buffer_threshold=90.0
            )
            config.validate()

    async def test_config_integration(self):
        """Test configuration integration with components."""
        # Create AlertConfig
        alert_config = AlertConfig(**self.test_config["alert"])
        
        # Test integration with MonitoringCoordinator
        coordinator = MonitoringCoordinator()
        
        # Register a thread and verify configuration is respected
        thread_id = coordinator.register_thread()
        self.assertTrue(coordinator.is_thread_registered(thread_id))
        
        # Cleanup should work with configured values
        await coordinator.cleanup()
        self.assertFalse(coordinator.is_thread_registered(thread_id))

    async def test_config_persistence(self):
        """Test configuration persistence."""
        # Create test configuration
        config = AlertConfig(**self.test_config["alert"])
        
        # Convert to dict for serialization
        config_dict = {
            "cpu_threshold": config.cpu_threshold,
            "memory_threshold": config.memory_threshold,
            "storage_latency_threshold": config.storage_latency_threshold,
            "buffer_threshold": config.buffer_threshold
        }
        
        # Mock file operations
        mock_config_data = json.dumps({"alert": config_dict})
        with patch("builtins.open", mock_open()) as mock_file:
            # Write configuration
            config_path = Path("config.json")
            with open(config_path, "w") as f:
                json.dump({"alert": config_dict}, f)
            
            # Verify write operation
            mock_file.assert_called_once_with(config_path, "w")
            mock_file().write.assert_called_once_with(mock_config_data)

    async def test_config_defaults(self):
        """Test configuration defaults."""
        # Create config with minimal parameters
        config = AlertConfig()
        
        # Verify default values
        self.assertEqual(config.cpu_threshold, 80.0)
        self.assertEqual(config.memory_threshold, 100.0)
        self.assertEqual(config.storage_latency_threshold, 0.5)
        self.assertEqual(config.buffer_threshold, 90.0)
        
        # Validate defaults are valid
        config.validate()  # Should not raise


if __name__ == '__main__':
    unittest.main()
