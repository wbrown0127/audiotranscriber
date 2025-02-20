import unittest
import asyncio
import os
import numpy as np
import time
import logging
from unittest.mock import Mock, patch
import pyaudiowpatch as pyaudio

from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.signal_processor import SignalProcessor
from audio_transcriber.storage_manager import StorageManager
from audio_transcriber.windows_manager import WindowsManager
from audio_transcriber.audio_transcriber import AudioTranscriber

class TestAudioCapture(unittest.TestCase):
    def setUp(self):
        self.coordinator = MonitoringCoordinator()
        self.coordinator.start_monitoring()
        self.capture = AdaptiveAudioCapture(self.coordinator)
        
    def tearDown(self):
        self.capture.stop_capture()
        self.coordinator.request_shutdown()
        
    def test_performance_monitoring(self):
        stats = self.capture.get_performance_stats()
        self.assertIn('cpu_usage', stats)
        self.assertIn('temperature', stats)
        self.assertIn('stream_health', stats)
        
    def test_buffer_adjustment(self):
        monitor = self.capture.monitor
        # Test high CPU scenario
        monitor.get_cpu_stats = Mock(return_value=(85.0, 70.0))
        monitor.reset_cooldown()  # Reset cooldown before testing adjustment
        self.assertTrue(monitor.should_adjust(85.0, 70.0))
        new_size = monitor.adjust_buffer_size()
        self.assertGreater(new_size, monitor.buffer_sizes[0])
        
    def test_wasapi_recovery(self):
        """Test recovery with real loopback device."""
        # Use same device indices as test_wasapi_stability.py
        system_loopback_device = 31  # Speakers (Realtek) [Loopback]
        
        wasapi = self.capture.wasapi
        
        # Initialize stream with system loopback device
        success = wasapi.initialize_stream(device_index=system_loopback_device)
        self.assertTrue(success)
        
        # Simulate stream failure
        wasapi.coordinator.update_state(stream_health=False)
        
        # Wait for recovery
        time.sleep(2.0)  # Allow time for recovery
        
        # Verify recovery
        state = wasapi.coordinator.get_state()
        self.assertTrue(state.stream_health)
        
        # Clean up
        wasapi.cleanup()

class TestSignalProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = SignalProcessor()
        
    def test_memory_management(self):
        self.processor.memory_threshold = 1024  # Low threshold for testing
        self.assertTrue(self.processor.should_cleanup())
        
    def test_audio_processing(self):
        # Create test audio data
        test_data = np.sin(2 * np.pi * 440 * np.arange(48000) / 48000)
        test_bytes = (test_data * 32767).astype(np.int16).tobytes()
        
        processed_channels, stats_channels = self.processor.process_audio(test_bytes, width=2)
        self.assertIsNotNone(processed_channels)
        self.assertIsNotNone(stats_channels)
        left_stats, right_stats = stats_channels
        self.assertTrue(0 <= left_stats.peak <= 1.0)
        self.assertTrue(0 <= right_stats.peak <= 1.0)
        
    def test_fallback_processing(self):
        result = self.processor.emergency_fallback(b'\x00\x80' * 1000)
        self.assertIsInstance(result, bytes)

class TestStorageManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = "test_storage"
        os.makedirs(self.test_dir, exist_ok=True)
        self.storage = StorageManager(self.test_dir)
        await self.storage.initialize()
        
    async def test_write_performance(self):
        test_data = b'\x00\x00' * 48000
        filename = os.path.join(self.test_dir, "test.raw")
        
        await self.storage.optimized_write(test_data, filename)
        stats = self.storage.get_performance_stats()
        
        self.assertLess(stats['write_latency'], 0.5)  # Allow up to 500ms for test environment
        self.assertGreater(stats['throughput'], 0)
        
    async def test_emergency_recovery(self):
        # Simulate write failure
        test_data = b'\x00\x00' * 48000
        self.storage.write_buffer.append((test_data, "failed.raw"))
        
        await self.storage.emergency_flush()
        backup_files = os.listdir(self.storage.emergency_dir)
        self.assertGreater(len(backup_files), 0)
        
    async def asyncTearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)

class TestWindowsManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = f"test_windows_{int(time.time() * 1000)}"
        os.makedirs(os.path.join(self.test_dir, "logs"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, "logs", "recovery"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, "logs", "analytics"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, "logs", "debug"), exist_ok=True)
        self.windows = WindowsManager(base_path=self.test_dir)
        
    def tearDown(self):
        try:
            # Close any open log handlers
            for handler in logging.getLogger().handlers[:]:
                handler.close()
                logging.getLogger().removeHandler(handler)
        finally:
            import shutil
            if os.path.exists(self.test_dir):
                shutil.rmtree(self.test_dir)
        
    def test_version_detection(self):
        version = self.windows.version
        self.assertIn(version.value, ["Windows 10", "Windows 11", "Unknown"])
        
    def test_mmcss_setup(self):
        result = self.windows.setup_mmcss()
        self.assertIsInstance(result, bool)
        
    def test_api_fallback(self):
        self.windows.fallback_enabled = True
        result = self.windows.safe_api_call(
            "audio", 
            "CreateAudioGraph",
            sample_rate=48000
        )
        self.assertIsNotNone(result)

class TestAudioTranscriber(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.base_path = f"test_transcriber_{int(time.time() * 1000)}"  # Unique path for each test
        self.transcriber = AudioTranscriber(self.base_path)
        
    async def test_initialization(self):
        try:
            # Initialize with real device
            success = await self.transcriber.initialize()
            self.assertTrue(success)
            
            # Verify directory structure
            expected_dirs = ["recordings", "logs", "temp", "backup"]
            for d in expected_dirs:
                path = os.path.join(self.base_path, d)
                self.assertTrue(os.path.exists(path))
                
            # Verify stream health
            state = self.transcriber.coordinator.get_state()
            self.assertTrue(state.stream_health)
        finally:
            # Close all log handlers before cleanup
            for handler in self.transcriber.logger.handlers[:]:
                handler.close()
                self.transcriber.logger.removeHandler(handler)
            
    async def test_health_monitoring(self):
        try:
            # Initialize with real device
            await self.transcriber.initialize()
            
            # Initialize status with required components
            self.transcriber.coordinator.update_state(
                components={
                    'capture': {
                        'cpu_usage': 0.0,
                        'stream_health': True
                    }
                }
            )
            
            # Perform health check
            await self.transcriber.check_system_health()
            status = self.transcriber.get_status()
            
            # Verify health metrics
            self.assertIn('system_status', status)
            self.assertIn('error_count', status)
            self.assertIn('components', status)
            
            # Verify stream health
            state = self.transcriber.coordinator.get_state()
            self.assertTrue(state.stream_health)
            
            # Verify performance stats
            self.assertIn('capture', status['components'])
            self.assertIn('cpu_usage', status['components']['capture'])
            self.assertIn('stream_health', status['components']['capture'])
        finally:
            # Close all log handlers before cleanup
            for handler in self.transcriber.logger.handlers[:]:
                handler.close()
                self.transcriber.logger.removeHandler(handler)
        
    async def test_recovery_system(self):
        try:
            # Initialize with real device
            await self.transcriber.initialize()
            
            # Simulate stream failure
            self.transcriber.coordinator.update_state(stream_health=False)
            self.transcriber.error_count = self.transcriber.max_errors
            
            # Allow time for recovery
            await self.transcriber.attempt_recovery()
            await asyncio.sleep(2.0)  # Give time for recovery to complete
            
            # Verify recovery
            state = self.transcriber.coordinator.get_state()
            self.assertTrue(state.stream_health)
            self.assertEqual(self.transcriber.error_count, 0)
        finally:
            # Close all log handlers before cleanup
            for handler in self.transcriber.logger.handlers[:]:
                handler.close()
                self.transcriber.logger.removeHandler(handler)
        
    async def asyncTearDown(self):
        await self.transcriber.cleanup()
        import shutil
        shutil.rmtree(self.base_path)

def run_tests():
    unittest.main(verbosity=2)

if __name__ == '__main__':
    run_tests()
