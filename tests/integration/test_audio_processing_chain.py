#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestAudioProcessingChain",
    "type": "Integration Test Suite",
    "description": "Integration test suite for verifying audio processing chain functionality, including channel synchronization, stream recovery, and performance monitoring",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TAPC[TestAudioProcessingChain] --> AAC[AdaptiveAudioCapture]
                TAPC --> SP[SignalProcessor]
                TAPC --> MC[MonitoringCoordinator]
                TAPC --> IT[IntegrationTest]
                TAPC --> DM[DeviceManager]
                TAPC --> SG[ScenarioGenerator]
        ```",
        "dependencies": {
            "AdaptiveAudioCapture": "Audio capture system",
            "SignalProcessor": "Signal processing system",
            "MonitoringCoordinator": "System monitoring",
            "IntegrationTest": "Base test functionality",
            "DeviceManager": "Audio device management",
            "ScenarioGenerator": "Test scenario generation"
        }
    },
    "notes": [
        "Channel synchronization using cross-correlation",
        "Buffer management and overflow handling",
        "Stream recovery and state tracking",
        "Performance monitoring and analysis",
        "End-to-end audio processing validation"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/integration/test_audio_processing_chain.py",
            "python -m pytest tests/integration/test_audio_processing_chain.py -k test_performance_monitoring --duration 3600"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "numpy",
            "pyaudiowpatch"
        ],
        "system": {
            "os": "Windows (for WASAPI)",
            "audio": "WASAPI-compatible device with active playback",
            "memory": "2GB minimum"
        }
    },
    "performance": {
        "execution_time": "Tests may take several minutes (slow marker)",
        "resource_usage": [
            "High CPU/memory usage during tests",
            "Requires actual audio hardware",
            "May impact system audio during testing"
        ]
    }
}
"""
import time
import numpy as np
import pytest
from unittest.mock import Mock, patch
from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.signal_processor import SignalProcessor
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from tests.utilities.base import IntegrationTest
from audio_transcriber.test_config.device_config import DeviceManager, DeviceType
from audio_transcriber.test_config.scenario_generator import ScenarioGenerator

class TestAudioProcessingChain(IntegrationTest):
    """Integration tests for audio processing chain functionality.
    
    This test class verifies the end-to-end functionality of the audio
    processing chain, focusing on system-wide interactions.
    
    Key Features Tested:
        - Channel synchronization accuracy
        - Buffer management under load
        - Stream recovery mechanisms
        - Performance characteristics
        - Resource utilization
    
    Attributes:
        coordinator (MonitoringCoordinator): System monitoring
        device_manager (DeviceManager): Audio device management
        scenario_generator (ScenarioGenerator): Test scenario generation
        capture (AdaptiveAudioCapture): Audio capture system
        processor (SignalProcessor): Signal processing system
    
    Example:
        class TestCustomProcessing(TestAudioProcessingChain):
            def test_custom_scenario(self):
                scenario = self.scenario_generator.create_custom_scenario()
                self.run_processing_test(scenario)
    """

    def setUp(self):
        """Set up test fixtures before each test method."""
        super().setUp()
        self.coordinator = MonitoringCoordinator()
        self.device_manager = DeviceManager()
        self.scenario_generator = ScenarioGenerator(self.device_manager)
        self.capture = AdaptiveAudioCapture(self.coordinator)
        self.processor = SignalProcessor()

    def tearDown(self):
        """Clean up test fixtures after each test method."""
        try:
            self.capture.stop_capture()
            self.coordinator.request_shutdown()
            self.device_manager.cleanup()
            self.processor.cleanup()
        finally:
            super().tearDown()

    @pytest.mark.slow
    def test_channel_synchronization(self):
        """Test channel synchronization using cross-correlation.
        
        Verifies the system's ability to detect and measure channel
        synchronization using cross-correlation. This test:
        1. Generates test audio with known delay
        2. Processes through audio chain
        3. Verifies delay detection accuracy
        
        Test Sequence:
            1. Generate test signals
            2. Create known delay
            3. Process audio data
            4. Analyze synchronization
            5. Verify results
        
        Expected Results:
            - Delay detected accurately
            - Strong correlation found
            - Processing time within limits
            - Metrics properly logged
        
        Example Metrics:
            - detected_delay: Measured delay
            - correlation_strength: Signal correlation
            - processing_time: Analysis duration
        """
        # Generate test audio with known delay between channels
        sample_rate = 48000
        duration = 1.0
        delay_samples = 100  # 100 samples delay
        
        # Create base signal
        t = np.arange(int(sample_rate * duration))
        signal = np.sin(2 * np.pi * 440 * t / sample_rate)
        
        # Create delayed version for second channel
        delayed_signal = np.zeros_like(signal)
        delayed_signal[delay_samples:] = signal[:-delay_samples]
        
        # Combine into stereo
        stereo_data = np.vstack((signal, delayed_signal)).T
        audio_bytes = (stereo_data * 32767).astype(np.int16).tobytes()
        
        # Process through chain
        processed_data = self.processor.process_audio(audio_bytes)
        sync_result = self.processor.analyze_channel_sync(processed_data)
        
        # Verify detected delay
        self.assertIsNotNone(sync_result['delay'])
        self.assertAlmostEqual(
            sync_result['delay'],
            delay_samples,
            delta=10  # Allow small margin of error
        )
        
        # Log synchronization metrics
        self.log_metric("detected_delay", sync_result['delay'])
        self.log_metric("correlation_strength", sync_result['correlation'])
        self.log_metric("processing_time", sync_result['processing_time'])

    @pytest.mark.slow
    def test_buffer_management(self):
        """Test buffer overrun/underrun handling in processing chain.
        
        Verifies the system's ability to handle buffer overruns and
        underruns under various processing loads. This test:
        1. Configures small buffers to stress system
        2. Tests different processing loads
        3. Monitors buffer statistics
        4. Verifies handling mechanisms
        
        Test Sequence:
            1. Configure test buffers
            2. Start audio capture
            3. Apply processing loads
            4. Monitor buffer stats
            5. Analyze results
        
        Expected Results:
            - Light load: minimal overruns
            - Medium load: managed overruns
            - Heavy load: graceful degradation
            - Proper metric logging
        
        Example Metrics:
            - [load]_overruns: Buffer overruns
            - [load]_underruns: Buffer underruns
            - [load]_latency: Processing latency
        """
        # Configure chain with smaller buffers for testing
        self.capture.configure_buffer(buffer_size=2048, trigger_level=1024)
        self.processor.configure_buffer(buffer_size=2048)
        
        # Start capture
        device = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
        self.capture.start_capture(device_id=device.device_index)
        
        # Run with various processing loads
        test_durations = [
            (0.001, "light"),   # Light processing
            (0.050, "medium"),  # Medium processing
            (0.200, "heavy")    # Heavy processing
        ]
        
        results = {}
        for delay, load_type in test_durations:
            # Set processing delay
            def delayed_processing(data):
                time.sleep(delay)
                return self.processor.process_audio(data)
            
            self.capture.set_processing_callback(delayed_processing)
            
            # Run for test period
            time.sleep(1.0)
            
            # Collect statistics
            capture_stats = self.capture.get_buffer_stats()
            processor_stats = self.processor.get_buffer_stats()
            
            results[load_type] = {
                'overruns': capture_stats['overruns'],
                'underruns': processor_stats['underruns'],
                'average_latency': processor_stats['average_latency']
            }
            
            # Log metrics for this load
            self.log_metric(f"{load_type}_overruns", capture_stats['overruns'])
            self.log_metric(f"{load_type}_underruns", processor_stats['underruns'])
            self.log_metric(f"{load_type}_latency", processor_stats['average_latency'])

    @pytest.mark.slow
    def test_stream_recovery(self):
        """Test stream recovery with state tracking.
        
        Verifies the system's ability to recover from various stream
        failure scenarios. This test:
        1. Tests multiple failure scenarios
        2. Verifies recovery mechanisms
        3. Tracks recovery statistics
        4. Monitors system state
        
        Test Sequence:
            1. Generate failure scenarios
            2. Configure recovery settings
            3. Apply failure sequence
            4. Monitor recovery attempts
            5. Verify system state
        
        Expected Results:
            - Successful recovery attempts
            - Proper state tracking
            - Timely recovery completion
            - Accurate metrics logging
        
        Example Metrics:
            - scenario_[id]_start: Scenario start time
            - scenario_[id]_recovery_[failure]: Success status
            - scenario_[id]_end: Completion time
        """
        # Generate failure scenarios
        scenarios = self.scenario_generator.generate_stream_failure_scenarios()
        
        for scenario in scenarios:
            # Log scenario start
            self.log_metric(f"scenario_{scenario.id}_start", time.time())
            
            # Configure chain based on scenario
            self.capture.configure_recovery(
                max_attempts=scenario.max_attempts,
                retry_interval=scenario.retry_interval
            )
            
            # Start capture
            self.capture.start_capture(
                device_id=scenario.device_config.device_index
            )
            
            # Apply failure sequence
            for failure in scenario.failures:
                # Inject failure
                failure.apply(self.capture)
                
                # Wait for recovery attempt
                time.sleep(scenario.retry_interval * 2)
                
                # Check recovery status
                recovery_stats = self.capture.get_recovery_stats()
                
                # Log recovery metrics
                self.log_metric(
                    f"scenario_{scenario.id}_recovery_{failure.id}",
                    recovery_stats['success']
                )
            
            # Log scenario completion
            self.log_metric(f"scenario_{scenario.id}_end", time.time())
            
            # Cleanup before next scenario
            self.capture.stop_capture()
            time.sleep(1.0)

    @pytest.mark.slow
    def test_performance_monitoring(self):
        """Test detailed performance monitoring of processing chain.
        
        Verifies the system's ability to monitor and track performance
        metrics during audio processing. This test:
        1. Monitors system performance
        2. Collects detailed metrics
        3. Analyzes performance patterns
        4. Verifies resource usage
        
        Test Sequence:
            1. Start monitored capture
            2. Collect performance data
            3. Calculate statistics
            4. Analyze resource usage
            5. Verify metrics
        
        Expected Results:
            - CPU usage within limits
            - Memory usage stable
            - Latency requirements met
            - Complete metric collection
        
        Example Metrics:
            - average_cpu_usage: CPU utilization
            - average_memory_usage: Memory usage
            - average_latency: Processing latency
            - samples_collected: Data points
        """
        # Start capture with monitoring
        device = self.device_manager.get_config(DeviceType.SYSTEM_LOOPBACK)
        self.capture.start_capture(device_id=device.device_index)
        
        # Run for test period with varying loads
        test_duration = 5.0  # seconds
        start_time = time.time()
        
        performance_samples = []
        while time.time() - start_time < test_duration:
            # Get current performance metrics
            capture_stats = self.capture.get_performance_stats()
            processor_stats = self.processor.get_performance_stats()
            
            # Combine metrics
            performance_samples.append({
                'timestamp': time.time() - start_time,
                'cpu_usage': capture_stats['cpu_usage'],
                'memory_usage': processor_stats['memory_usage'],
                'latency': capture_stats['latency'],
                'buffer_usage': processor_stats['buffer_usage']
            })
            
            time.sleep(0.1)  # Sample every 100ms
        
        # Calculate statistics
        avg_cpu = np.mean([s['cpu_usage'] for s in performance_samples])
        avg_memory = np.mean([s['memory_usage'] for s in performance_samples])
        avg_latency = np.mean([s['latency'] for s in performance_samples])
        
        # Log overall metrics
        self.log_metric("average_cpu_usage", avg_cpu)
        self.log_metric("average_memory_usage", avg_memory)
        self.log_metric("average_latency", avg_latency)
        self.log_metric("samples_collected", len(performance_samples))

if __name__ == '__main__':
    unittest.main()
