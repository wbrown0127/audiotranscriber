import unittest
import asyncio
import os
import time
import logging
from datetime import datetime, timedelta
from audio_transcriber.audio_transcriber import AudioTranscriber
from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.signal_processor import SignalProcessor
from audio_transcriber.storage_manager import StorageManager
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator

class TestLongTermStability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create unique test directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.base_path = f"test_stability_{timestamp}"
        os.makedirs(self.base_path, exist_ok=True)
        
        # Setup logging
        log_path = os.path.join(self.base_path, "stability_test.log")
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("StabilityTest")
        
        # Initialize coordinator
        self.coordinator = MonitoringCoordinator()
        self.coordinator.start_monitoring()
        
        # Initialize components
        self.transcriber = AudioTranscriber(self.base_path)
        self.capture = AdaptiveAudioCapture(self.coordinator)
        self.processor = SignalProcessor()
        self.storage = StorageManager(self.base_path)
        
        # Performance tracking
        self.perf_stats = []
        self.error_counts = {
            'audio': 0,
            'processing': 0,
            'storage': 0,
            'recovery': 0
        }
        
    async def test_24hour_continuous_operation(self):
        """Test system stability over 24 hours of continuous operation."""
        self.logger.info("Starting 24-hour stability test")
        
        # Test duration and check interval
        duration = timedelta(hours=24)
        check_interval = 300  # 5 minutes
        start_time = datetime.now()
        end_time = start_time + duration
        
        try:
            await self.transcriber.initialize()
            self.logger.info("System initialized successfully")
            
            while datetime.now() < end_time:
                # Collect performance metrics
                stats = {
                    'timestamp': datetime.now().isoformat(),
                    'cpu': self.capture.get_performance_stats(),
                    'memory': self.processor.get_performance_stats(),
                    'storage': self.storage.get_performance_stats(),
                    'system': self.transcriber.get_status()
                }
                self.perf_stats.append(stats)
                
                # Check system health
                await self.check_system_health()
                
                # Log current status
                self.log_current_status(stats)
                
                # Verify thresholds
                self.verify_performance_thresholds(stats)
                
                # Wait for next check interval
                await asyncio.sleep(check_interval)
                
            # Test completion
            self.logger.info("24-hour test completed successfully")
            self.analyze_results()
            
        except Exception as e:
            self.logger.error(f"Test failed: {e}")
            raise
            
    async def check_system_health(self):
        """Verify all system components are functioning correctly."""
        try:
            # Check audio capture and WASAPI stability
            capture_stats = self.capture.get_performance_stats()
            wasapi = self.capture.wasapi
            
            # Check stream health and performance
            if capture_stats['cpu_usage'] > 80 or not capture_stats['stream_health']:
                self.error_counts['audio'] += 1
                self.logger.warning("Audio capture issues detected")
                
            # Check audio sessions
            if not wasapi.session_monitor.active_sessions:
                self.logger.warning("No active audio sessions detected")
                
            # Check device stability
            device_info = wasapi.get_wasapi_devices()
            current_device = wasapi.stream._device_index if hasattr(wasapi, 'stream') else None
            if current_device is not None and current_device not in device_info:
                self.error_counts['audio'] += 1
                self.logger.error("Current audio device no longer available")
                
            # Check recovery status
            if wasapi.recovery_attempts > 0:
                self.error_counts['recovery'] += 1
                self.logger.warning(f"Recovery attempts: {wasapi.recovery_attempts}")
                
            # Check signal processing
            if self.processor.should_cleanup():
                self.error_counts['processing'] += 1
                self.logger.warning("High memory usage in signal processor")
                
            # Check storage
            storage_stats = self.storage.get_performance_stats()
            if storage_stats['write_latency'] > 0.5:  # 500ms threshold
                self.error_counts['storage'] += 1
                self.logger.warning("Storage write latency issues")
                
            # Check recovery system
            system_status = self.transcriber.get_status()
            if system_status['error_count'] > 0:
                self.error_counts['recovery'] += 1
                self.logger.warning("System recovery triggered")
                
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            
    def verify_performance_thresholds(self, stats):
        """Verify system stays within performance thresholds."""
        # CPU Usage
        if stats['cpu']['cpu_usage'] > 80:
            self.logger.warning(f"High CPU usage: {stats['cpu']['cpu_usage']}%")
            
        # Memory Usage
        if stats['memory']['memory_usage'] > 100 * 1024 * 1024:  # 100MB
            self.logger.warning(f"High memory usage: {stats['memory']['memory_usage'] / 1024 / 1024}MB")
            
        # Storage Performance
        if stats['storage']['write_latency'] > 0.5:
            self.logger.warning(f"High write latency: {stats['storage']['write_latency']}s")
            
    def log_current_status(self, stats):
        """Log current system status and performance metrics."""
        self.logger.info(
            f"Status Report:\n"
            f"CPU Usage: {stats['cpu']['cpu_usage']}%\n"
            f"Memory Usage: {stats['memory']['memory_usage'] / 1024 / 1024:.2f}MB\n"
            f"Write Latency: {stats['storage']['write_latency']*1000:.2f}ms\n"
            f"Error Counts: {self.error_counts}"
        )
        
    def analyze_results(self):
        """Analyze test results and generate summary."""
        # Calculate statistics
        cpu_usage = [s['cpu']['cpu_usage'] for s in self.perf_stats]
        memory_usage = [s['memory']['memory_usage'] for s in self.perf_stats]
        write_latency = [s['storage']['write_latency'] for s in self.perf_stats]
        
        # Calculate WASAPI specific metrics
        wasapi_stats = []
        for stat in self.perf_stats:
            if 'wasapi' not in stat:
                continue
            wasapi_stats.append({
                'recovery_attempts': stat['wasapi'].get('recovery_attempts', 0),
                'stream_health': stat['wasapi'].get('stream_health', True),
                'active_sessions': len(stat['wasapi'].get('active_sessions', [])),
                'buffer_size': stat['wasapi'].get('buffer_size', 0)
            })
        
        # Calculate WASAPI metrics if available
        wasapi_summary = {}
        if wasapi_stats:
            recovery_attempts = [s['recovery_attempts'] for s in wasapi_stats]
            stream_health = [1 if s['stream_health'] else 0 for s in wasapi_stats]
            active_sessions = [s['active_sessions'] for s in wasapi_stats]
            buffer_sizes = [s['buffer_size'] for s in wasapi_stats]
            
            wasapi_summary = {
                'recovery_attempts': {
                    'total': sum(recovery_attempts),
                    'max_consecutive': max(recovery_attempts)
                },
                'stream_health': {
                    'uptime_percent': (sum(stream_health) / len(stream_health)) * 100
                },
                'active_sessions': {
                    'avg': sum(active_sessions) / len(active_sessions),
                    'max': max(active_sessions)
                },
                'buffer_size': {
                    'avg': sum(buffer_sizes) / len(buffer_sizes),
                    'min': min(buffer_sizes),
                    'max': max(buffer_sizes)
                }
            }
        
        summary = {
            'duration': '24 hours',
            'cpu_usage': {
                'avg': sum(cpu_usage) / len(cpu_usage),
                'max': max(cpu_usage)
            },
            'memory_usage': {
                'avg': sum(memory_usage) / len(memory_usage) / 1024 / 1024,
                'max': max(memory_usage) / 1024 / 1024
            },
            'write_latency': {
                'avg': sum(write_latency) / len(write_latency) * 1000,
                'max': max(write_latency) * 1000
            },
            'error_counts': self.error_counts,
            'wasapi': wasapi_summary
        }
        
        # Log summary
        self.logger.info(
            f"\nTest Summary:\n"
            f"Duration: {summary['duration']}\n"
            f"CPU Usage - Avg: {summary['cpu_usage']['avg']:.2f}%, Max: {summary['cpu_usage']['max']:.2f}%\n"
            f"Memory Usage - Avg: {summary['memory_usage']['avg']:.2f}MB, Max: {summary['memory_usage']['max']:.2f}MB\n"
            f"Write Latency - Avg: {summary['write_latency']['avg']:.2f}ms, Max: {summary['write_latency']['max']:.2f}ms\n"
            f"Total Errors: {sum(self.error_counts.values())}\n"
            f"Error Breakdown: {self.error_counts}\n"
            f"\nWASAPI Performance:\n"
            f"Stream Uptime: {summary['wasapi']['stream_health']['uptime_percent']:.2f}%\n"
            f"Recovery Attempts: {summary['wasapi']['recovery_attempts']['total']} (Max Consecutive: {summary['wasapi']['recovery_attempts']['max_consecutive']})\n"
            f"Active Sessions - Avg: {summary['wasapi']['active_sessions']['avg']:.1f}, Max: {summary['wasapi']['active_sessions']['max']}\n"
            f"Buffer Size - Avg: {summary['wasapi']['buffer_size']['avg']:.0f}, Range: {summary['wasapi']['buffer_size']['min']}-{summary['wasapi']['buffer_size']['max']} frames"
        )
        
    async def asyncTearDown(self):
        """Cleanup test resources."""
        try:
            # Stop components
            self.capture.stop_capture()
            self.coordinator.request_shutdown()
            await self.transcriber.cleanup()
            
            # Keep the log file but clean up other test data
            if os.path.exists(self.base_path):
                for item in os.listdir(self.base_path):
                    if not item.endswith('.log'):
                        path = os.path.join(self.base_path, item)
                        if os.path.isfile(path):
                            os.remove(path)
                        elif os.path.isdir(path):
                            import shutil
                            shutil.rmtree(path)
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")

def run_stability_tests():
    """Run stability tests with custom test runner."""
    unittest.main(verbosity=2)

if __name__ == '__main__':
    run_stability_tests()
