"""
Test Updates [2025-02-19]:
- Converted to pytest-asyncio for Python 3.13.1 compatibility
- Added resource management through MonitoringCoordinator
- Added proper lock ordering documentation
- Added comprehensive error context and validation

COMPONENT_NOTES:
{
    "name": "TestWindowsManager",
    "type": "Test Suite",
    "description": "Core test suite for verifying Windows system management functionality, including MMCSS setup, API fallbacks, version detection, and resource management",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TWM[TestWindowsManager] --> WM[WindowsManager]
                TWM --> MC[MonitoringCoordinator]
                TWM --> RL[RecoveryLogger]
                TWM --> CT[ComponentTest]
                WM --> MMCSS[MMCSSManager]
                WM --> API[APIManager]
                WM --> VD[VersionDetector]
                WM --> FB[FallbackHandler]
                WM --> MC
        ```",
        "dependencies": {
            "WindowsManager": "Main component under test",
            "MonitoringCoordinator": "System monitoring and resource management",
            "RecoveryLogger": "Error logging and recovery",
            "ComponentTest": "Base test functionality",
            "MMCSSManager": "Multimedia Class Scheduler",
            "APIManager": "Windows API interface",
            "VersionDetector": "Windows version detection",
            "FallbackHandler": "API fallback mechanisms"
        }
    },
    "notes": [
        "Tests Windows version detection",
        "Verifies MMCSS setup and status",
        "Tests API fallback mechanisms",
        "Validates error handling",
        "Tests recovery logging",
        "Ensures proper cleanup",
        "Uses async patterns for real-time processing",
        "Manages resources through coordinator"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_windows_manager.py",
            "python -m pytest tests/core/test_windows_manager.py -k test_mmcss_setup"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "pytest-asyncio",
            "logging",
            "os"
        ],
        "system": {
            "os": "Windows 10/11",
            "permissions": "Admin rights for MMCSS"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Light system API usage",
            "Minimal disk I/O for logs",
            "Proper cleanup of system resources"
        ]
    }
}
"""
import os
import logging
import pytest
from audio_transcriber.windows_manager import WindowsManager
from audio_transcriber.recovery_logger import RecoveryLogger
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import ComponentTest

# Lock order documentation for reference:
# 1. state_lock: Component state transitions
# 2. metrics_lock: Performance metrics updates
# 3. perf_lock: Performance data collection
# 4. component_lock: Component lifecycle management
# 5. update_lock: Resource updates and allocation

@pytest.mark.asyncio
class TestWindowsManager(ComponentTest):
    async def asyncSetUp(self):
        """Set up test environment."""
        await super().setUp()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            # Create test directory structure with absolute path
            self.test_dir = os.path.abspath(os.path.join("tests", "results", f"test_windows_{self.test_id}"))
            for subdir in ["logs", "logs/recovery", "logs/analytics", "logs/debug"]:
                os.makedirs(os.path.join(self.test_dir, subdir), exist_ok=True)
                
            # Initialize coordinator with proper setup and resource management
            self.coordinator = MonitoringCoordinator()
            await self.coordinator.start_monitoring()
                
            # Initialize recovery logger first
            self.recovery_logger = RecoveryLogger(self.test_dir)
            await self.recovery_logger.start_session()
            
            # Register recovery logger with coordinator
            await self.coordinator.register_component(self.recovery_logger)
                
            # Initialize windows manager with coordinator and recovery logger
            self.windows = WindowsManager(
                base_path=self.test_dir,
                coordinator=self.coordinator
            )
            self.windows.recovery_logger = self.recovery_logger
            
            # Register windows manager with coordinator
            await self.coordinator.register_component(self.windows)
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}", exc_info=True)
            raise
        
    async def asyncTearDown(self):
        """Clean up test environment."""
        try:
            # Follow proper lock ordering during cleanup
            if hasattr(self, 'windows'):
                await self.coordinator.unregister_component(self.windows)
                await self.windows.cleanup()
            
            if hasattr(self, 'recovery_logger'):
                await self.coordinator.unregister_component(self.recovery_logger)
                await self.recovery_logger.end_session()
            
            if hasattr(self, 'coordinator'):
                # Ensure proper resource cleanup
                await self.coordinator.stop_monitoring()
                await self.coordinator.cleanup_resources()
                await self.coordinator.request_shutdown()
                
                # Verify all resources are properly released
                stats = await self.coordinator.get_resource_stats()
                assert stats['active_buffers'] == 0, "Resource leak detected"
                
            # Close any open log handlers
            for handler in logging.getLogger().handlers[:]:
                handler.close()
                logging.getLogger().removeHandler(handler)
                
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}", exc_info=True)
            raise
        finally:
            # Remove test directory
            import shutil
            if os.path.exists(self.test_dir):
                shutil.rmtree(self.test_dir)
            await super().tearDown()
        
    @pytest.mark.fast
    async def test_version_detection(self):
        """Test Windows version detection with resource management."""
        try:
            # Get Windows version
            version = await self.windows.get_version()
            
            # Verify version is valid
            self.assertIn(version.value, ["Windows 10", "Windows 11", "Unknown"])
            
            # Log version info
            await self.log_metric("windows_version", version.value)
            await self.log_metric("is_windows_11", version.value == "Windows 11")
            
            # Verify resource state
            stats = await self.coordinator.get_resource_stats()
            self.assertEqual(stats['active_version_checks'], 0)
            
        except Exception as e:
            self.logger.error(f"Version detection test failed: {e}", exc_info=True)
            raise
        
    @pytest.mark.fast
    async def test_mmcss_setup(self):
        """Test Multimedia Class Scheduler Service setup with resource management."""
        try:
            # Allocate buffer for MMCSS setup
            buffer = await self.coordinator.allocate_buffer('small')
            
            try:
                # Attempt MMCSS setup
                result = await self.windows.setup_mmcss(buffer)
                
                # Verify result
                self.assertIsInstance(result, bool)
                
                # Get MMCSS status
                status = await self.windows.get_mmcss_status()
                
                # Log MMCSS metrics
                await self.log_metric("mmcss_setup_success", result)
                await self.log_metric("mmcss_enabled", status.get('enabled', False))
                await self.log_metric("mmcss_task_index", status.get('task_index', -1))
                
                # Verify resource state
                stats = await self.coordinator.get_resource_stats()
                self.assertEqual(stats['active_mmcss_tasks'], int(status.get('enabled', False)))
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"MMCSS setup test failed: {e}", exc_info=True)
            raise
        
    @pytest.mark.fast
    async def test_api_fallback(self):
        """Test API fallback mechanisms with resource management."""
        try:
            # Allocate buffer for API calls
            buffer = await self.coordinator.allocate_buffer('small')
            
            try:
                # Enable fallback mode
                await self.windows.enable_fallback()
                
                # Test audio API call with fallback
                result = await self.windows.safe_api_call(
                    "audio",
                    "CreateAudioGraph",
                    buffer=buffer,
                    sample_rate=48000
                )
                
                # Verify fallback result
                self.assertIsNotNone(result)
                
                # Get fallback stats
                stats = await self.windows.get_fallback_stats()
                
                # Log fallback metrics
                await self.log_metric("fallback_enabled", await self.windows.is_fallback_enabled())
                await self.log_metric("fallback_calls", stats.get('total_calls', 0))
                await self.log_metric("successful_fallbacks", stats.get('successful', 0))
                
                # Verify resource state
                resource_stats = await self.coordinator.get_resource_stats()
                self.assertEqual(resource_stats['active_api_calls'], 0)
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"API fallback test failed: {e}", exc_info=True)
            raise
        
    @pytest.mark.fast
    async def test_error_handling(self):
        """Test Windows API error handling with resource management."""
        try:
            # Allocate buffer for error testing
            buffer = await self.coordinator.allocate_buffer('small')
            
            try:
                # Test invalid API call
                result = await self.windows.safe_api_call(
                    "invalid",
                    "InvalidFunction",
                    buffer=buffer,
                    invalid_param=True
                )
                
                # Verify error handling
                self.assertIsNone(result)
                
                # Get error stats
                error_stats = await self.windows.get_error_stats()
                coordinator_stats = await self.coordinator.get_error_stats()
                
                # Verify error tracking
                self.assertEqual(error_stats['total'], coordinator_stats['error_count'])
                self.assertIn('api_error', coordinator_stats['error_types'])
                
                # Log error metrics
                await self.log_metric("total_errors", error_stats.get('total', 0))
                await self.log_metric("handled_errors", error_stats.get('handled', 0))
                await self.log_metric("unhandled_errors", error_stats.get('unhandled', 0))
                
                # Verify resource state
                resource_stats = await self.coordinator.get_resource_stats()
                self.assertEqual(resource_stats['active_api_calls'], 0)
                
            finally:
                # Release buffer
                await self.coordinator.release_buffer(buffer)
                
        except Exception as e:
            self.logger.error(f"Error handling test failed: {e}", exc_info=True)
            raise
