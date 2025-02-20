"""
COMPONENT_NOTES:
{
    "name": "TestRealDevices",
    "type": "Integration Test Suite",
    "description": "Comprehensive test suite for verifying audio device behavior, recovery, and stability using real hardware",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TRD[TestRealDevices] --> WM[WASAPIMonitor]
                TRD --> MC[MonitoringCoordinator]
                TRD --> AC[AdaptiveAudioCapture]
                TRD --> RL[RecoveryLogger]
                TRD --> SM[StateMachine]
                TRD --> AS[AlertSystem]
                TRD --> DM[DeviceManager]
                TRD --> SG[ScenarioGenerator]
        ```",
        "dependencies": {
            "WASAPIMonitor": "Manages audio device interactions",
            "MonitoringCoordinator": "Coordinates system monitoring",
            "AdaptiveAudioCapture": "Handles audio capture operations",
            "RecoveryLogger": "Logs recovery events and metrics",
            "StateMachine": "Tracks system state transitions",
            "AlertSystem": "Manages performance alerts",
            "DeviceManager": "Manages test device configurations",
            "ScenarioGenerator": "Generates test scenarios"
        }
    },
    "notes": [
        "Verifies real device behavior and recovery",
        "Tests device switching and hot-plug handling",
        "Validates concurrent and cascading failures",
        "Monitors comprehensive performance metrics",
        "Requires specific hardware setup for full testing"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/integration/test_real_devices.py",
            "python -m pytest tests/integration/test_real_devices.py -k test_comprehensive_suite --duration 3600"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "pyaudiowpatch",
            "asyncio",
            "psutil"
        ],
        "system": {
            "os": "Windows (for WASAPI)",
            "audio": "Multiple WASAPI-compatible devices and VB-Cable",
            "memory": "4GB minimum"
        }
    },
    "performance": {
        "execution_time": "Tests may take several hours",
        "resource_usage": [
            "High CPU/memory usage",
            "Requires actual hardware",
            "May impact system stability",
            "Extensive logging generated"
        ]
    }
}


Example Usage:
    # Run all real device tests
    python -m pytest tests/integration/test_real_devices.py

    # Run specific test with extended duration
    python -m pytest tests/integration/test_real_devices.py -k test_comprehensive_suite --duration 3600

Test Requirements:
    - Python 3.13.1+
    - pytest with asyncio support
    - Multiple WASAPI-compatible devices
    - VB-Cable virtual audio device
    - Minimum 4GB available memory
    - Active audio playback

Hardware Requirements:
    - Multiple audio output devices
    - System loopback device enabled
    - USB audio device (recommended)
    - Stable audio drivers

Performance Considerations:
    - Tests may take several hours
    - High CPU/memory usage
    - Requires actual hardware
    - May impact system stability
    - Extensive logging generated
"""

from unittest import IsolatedAsyncioTestCase
import time
import psutil
import statistics
from pathlib import Path
from typing import List, Optional
import asyncio
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.wasapi_monitor import WASAPIMonitor
from audio_transcriber.audio_capture import AdaptiveAudioCapture
from audio_transcriber.recovery_logger import RecoveryLogger
from audio_transcriber.state_machine import StateMachine
from audio_transcriber.alert_system import AlertSystem, AlertConfig
from tests.test_config.device_config import DeviceManager, DeviceType
from audio_transcriber.test_config.scenario_generator import ScenarioGenerator, ScenarioConfig, create_test_suite

class TestRealDevices(IsolatedAsyncioTestCase):
    """Test suite for real device testing with comprehensive scenarios.
    
    This test class verifies the behavior of audio devices under real-world
    conditions, focusing on stability and recovery capabilities.
    
    Key Features Tested:
        - Basic device operations
        - Device switching scenarios
        - Concurrent failure handling
        - Cascading failure recovery
        - Random scenario combinations
        - Performance monitoring
    
    Attributes:
        device_manager (DeviceManager): Audio device management
        scenario_generator (ScenarioGenerator): Test scenario generation
        recovery_logger (RecoveryLogger): Recovery event logging
        state_machine (StateMachine): System state tracking
        coordinator (MonitoringCoordinator): System monitoring
        alert_system (AlertSystem): Performance alerting
    
    Example:
        class TestCustomDevices(TestRealDevices):
            async def test_custom_scenario(self):
                scenario = self.scenario_generator.create_custom_scenario()
                wasapi = WASAPIMonitor(self.coordinator)
                success = await self.verify_recovery_success(scenario)
                self.assertTrue(success)
    """

    @classmethod
    def setUpClass(cls):
        """Set up test environment and initialize device management."""
        cls.device_manager = DeviceManager()
        cls.scenario_generator = ScenarioGenerator(cls.device_manager)
        # Create test-specific logging directory
        cls.test_log_dir = Path("tests/results") / f"test_recovery_{int(time.time())}"
        cls.test_log_dir.mkdir(parents=True, exist_ok=True)
        cls.recovery_logger = RecoveryLogger(base_path=cls.test_log_dir)
        cls.state_machine = StateMachine()

    async def setUp(self):
        """Set up test environment for each test."""
        self.audio_queue = asyncio.Queue(maxsize=1000)
        
        # Initialize monitoring systems
        self.alert_system = AlertSystem(AlertConfig(
            cpu_threshold=80.0,
            memory_threshold=100.0,
            storage_latency_threshold=0.5,
            buffer_threshold=90.0
        ))
        
        # Initialize performance metrics
        self.performance_metrics = {
            'cpu_usage': [],
            'memory_usage': [],
            'latency': [],
            'buffer_usage': []
        }
        
        self.coordinator = MonitoringCoordinator(
            audio_queue=self.audio_queue,
            storage_manager=self.device_manager,
            alert_system=self.alert_system
        )
        
        # Start monitoring and logging
        await self.coordinator.start()
        self.recovery_logger.start_session()
        
        # Initialize monitoring timestamp
        self._last_check_time = time.perf_counter()
        
        # Start performance monitoring
        self._monitoring_task = asyncio.create_task(self._monitor_performance())

    async def tearDown(self):
        """Clean up test environment after each test."""
        # Cancel performance monitoring task
        if hasattr(self, '_monitoring_task'):
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        await self.coordinator.stop()  # Stop monitoring asynchronously
        self.recovery_logger.end_session()

    @classmethod
    def tearDownClass(cls):
        """Clean up shared resources."""
        if hasattr(cls, 'device_manager'):
            cls.device_manager.cleanup()

    async def _monitor_performance(self):
        """Monitor system performance metrics.
        
        Internal method to continuously monitor and log system performance
        metrics during test execution. This method:
        1. Monitors CPU, memory, latency, and buffer usage
        2. Tracks performance alerts
        3. Logs performance events
        4. Handles monitoring errors
        
        Performance Metrics:
            - CPU usage percentage
            - Memory usage (MB)
            - Processing latency
            - Buffer utilization
        
        Alert Types:
            - CPU threshold exceeded
            - Memory threshold exceeded
            - Storage latency issues
            - Buffer usage warnings
        
        Error Handling:
            - Logs monitoring errors
            - Implements backoff on failure
            - Maintains monitoring state
        """
        while True:
            try:
                # Get performance metrics
                cpu_alert = await self.alert_system.check_cpu_usage()
                memory_alert = await self.alert_system.check_memory_usage()
                latency_alert = await self.alert_system.check_storage_latency()
                buffer_alert = await self.alert_system.check_buffer_usage()
                
                # Store metrics
                self.performance_metrics['cpu_usage'].append(
                    psutil.cpu_percent())
                self.performance_metrics['memory_usage'].append(
                    psutil.Process().memory_info().rss / (1024 * 1024))
                self.performance_metrics['latency'].append(
                    time.perf_counter() - self._last_check_time)
                self.performance_metrics['buffer_usage'].append(
                    self.audio_queue.qsize() / self.audio_queue.maxsize * 100)
                
                self._last_check_time = time.perf_counter()
                
                # Log alerts if any
                for alert in [cpu_alert, memory_alert, latency_alert, buffer_alert]:
                    if alert.triggered:
                        self.recovery_logger.log_event(
                            'performance_alert',
                            {'message': alert.message}
                        )
                
                await asyncio.sleep(1)  # Check every second
            except Exception as e:
                self.recovery_logger.log_event(
                    'monitoring_error',
                    {'error': str(e)}
                )
                await asyncio.sleep(5)  # Back off on error

    async def verify_recovery_success(self, scenario: ScenarioConfig) -> bool:
        """Verify successful recovery from a test scenario.
        
        Verifies that the system can successfully recover from a given
        test scenario while monitoring performance impact. This method:
        1. Records initial system state
        2. Applies error sequence
        3. Monitors recovery process
        4. Verifies final state
        5. Logs performance metrics
        
        Args:
            scenario: Test scenario to verify recovery from
        
        Returns:
            bool: True if recovery was successful, False otherwise
        
        Example Metrics:
            - Initial/final CPU usage
            - Memory consumption
            - Buffer utilization
            - Recovery duration
        """
        # Record initial performance state
        initial_metrics = {
            'cpu': psutil.cpu_percent(),
            'memory': psutil.Process().memory_info().rss / (1024 * 1024),
            'buffer': self.audio_queue.qsize() / self.audio_queue.maxsize * 100
        }
        
        # Get initial state
        initial_state = self.coordinator.get_state()
        initial_time = time.perf_counter()
        
        # Apply error sequence
        for error in scenario.error_sequence:
            self.coordinator.update_state(stream_health=False, error_info=error)
            await asyncio.sleep(0.1)  # Allow time for error to register
            
        # Wait for expected recovery time
        await asyncio.sleep(scenario.expected_recovery_time)
        
        # Get final state and performance metrics
        final_state = self.coordinator.get_state()
        recovery_time = time.perf_counter() - initial_time
        final_metrics = {
            'cpu': psutil.cpu_percent(),
            'memory': psutil.Process().memory_info().rss / (1024 * 1024),
            'buffer': self.audio_queue.qsize() / self.audio_queue.maxsize * 100
        }
        
        # Log performance impact
        self.recovery_logger.log_event('recovery_performance', {
            'scenario': scenario.scenario_type,
            'recovery_time': recovery_time,
            'initial_metrics': initial_metrics,
            'final_metrics': final_metrics,
            'performance_impact': {
                metric: final_metrics[metric] - initial_metrics[metric]
                for metric in initial_metrics
            }
        })
        
        # Verify recovery
        recovery_successful = (
            final_state.stream_health and
            not final_state.error_info and
            self.recovery_logger.get_last_recovery_status() == 'success' and
            all(
                final_metrics[metric] <= self.alert_system.config.__dict__[f"{metric}_threshold"]
                for metric in ['cpu', 'memory']
            )
        )
        
        return recovery_successful

    async def test_basic_scenarios(self):
        """Test basic failure scenarios for each device type.
        
        Verifies system recovery from basic failure scenarios across
        different device types. This test:
        1. Tests each device type
        2. Applies basic failure scenarios
        3. Verifies recovery success
        4. Monitors performance impact
        
        Test Sequence:
            1. Generate basic scenarios
            2. Initialize each device
            3. Apply failure scenario
            4. Verify recovery
            5. Clean up resources
        
        Expected Results:
            - Successful initialization
            - Recovery from failures
            - Performance within limits
            - Proper cleanup
        
        Example Metrics:
            - Recovery success rate
            - Recovery time per scenario
            - Resource utilization
            - Error counts
            
        Note:
            Tests will be skipped for device types that are not available
            on the current system.
        """
        scenarios = self.scenario_generator.generate_basic_scenarios()
        skipped_devices = set()
        
        for scenario in scenarios:
            device_type = scenario.primary_device.device_type
            if device_type in skipped_devices:
                continue
                
            with self.subTest(scenario=scenario.scenario_type):
                try:
                    # Validate device availability
                    if not self.device_manager.validate_device(device_type):
                        logging.warning(f"Skipping tests for unavailable device type: {device_type.name}")
                        skipped_devices.add(device_type)
                        continue
                    
                    wasapi = WASAPIMonitor(self.coordinator)
                    
                    # Initialize with scenario's primary device
                    success = wasapi.initialize_stream(
                        device_index=scenario.primary_device.device_index
                    )
                    self.assertTrue(success)
                    
                    # Verify recovery from scenario
                    recovery_success = await self.verify_recovery_success(scenario)
                    self.assertTrue(
                        recovery_success,
                        f"Failed to recover from {scenario.scenario_type}"
                    )
                    
                finally:
                    if 'wasapi' in locals():
                        wasapi.cleanup()
                        
        # Log summary of skipped devices
        if skipped_devices:
            logging.info(f"Skipped tests for unavailable devices: {[d.name for d in skipped_devices]}")

    async def test_device_switching(self):
        """Test device switching scenarios.
        
        Verifies the system's ability to handle device switching
        operations smoothly. This test:
        1. Tests various device combinations
        2. Verifies switching behavior
        3. Monitors recovery process
        4. Tracks performance impact
        
        Test Sequence:
            1. Generate switch scenarios
            2. Initialize primary device
            3. Switch to secondary
            4. Verify recovery
            5. Monitor stability
        
        Expected Results:
            - Successful device switches
            - Clean recovery process
            - State consistency
            - No resource leaks
        
        Example Metrics:
            - Switch success rate
            - Switching time
            - Resource impact
            - Error handling
            
        Note:
            Tests will be skipped for device combinations where either
            the primary or secondary device is not available.
        """
        scenarios = self.scenario_generator.generate_device_switch_scenarios()
        skipped_combinations = set()
        
        for scenario in scenarios:
            combo = (scenario.primary_device.device_type, scenario.secondary_device.device_type)
            if combo in skipped_combinations:
                continue
                
            with self.subTest(devices=f"{scenario.primary_device.name}->{scenario.secondary_device.name}"):
                try:
                    # Validate both devices
                    if not (self.device_manager.validate_device(scenario.primary_device.device_type) and 
                           self.device_manager.validate_device(scenario.secondary_device.device_type)):
                        logging.warning(
                            f"Skipping switch test for unavailable device combination: "
                            f"{scenario.primary_device.name} -> {scenario.secondary_device.name}"
                        )
                        skipped_combinations.add(combo)
                        continue
                    
                    wasapi = WASAPIMonitor(self.coordinator)
                    
                    # Start with primary device
                    success = wasapi.initialize_stream(
                        device_index=scenario.primary_device.device_index
                    )
                    self.assertTrue(success)
                    
                    # Verify device switch recovery
                    recovery_success = await self.verify_recovery_success(scenario)
                    self.assertTrue(
                        recovery_success,
                        f"Failed to switch from {scenario.primary_device.name} to {scenario.secondary_device.name}"
                    )
                    
                finally:
                    if 'wasapi' in locals():
                        wasapi.cleanup()
                        
        # Log summary of skipped combinations
        if skipped_combinations:
            logging.info(
                "Skipped tests for unavailable device combinations: " +
                ", ".join([f"{p.name}->{s.name}" for p, s in skipped_combinations])
            )

    async def test_concurrent_failures(self):
        """Test scenarios with multiple simultaneous failures.
        
        Verifies the system's ability to handle and recover from
        multiple concurrent failures. This test:
        1. Simulates multiple failures
        2. Tests recovery mechanisms
        3. Verifies system stability
        4. Monitors resource usage
        
        Test Sequence:
            1. Generate concurrent scenarios
            2. Apply multiple failures
            3. Monitor recovery process
            4. Verify system state
            5. Check resource usage
        
        Expected Results:
            - Successful recovery
            - Proper error handling
            - Resource stability
            - Complete recovery
        
        Example Metrics:
            - Recovery success rate
            - Total recovery time
            - Resource utilization
            - Error resolution
            
        Note:
            Tests will be skipped for device types that are not available
            on the current system.
        """
        scenarios = self.scenario_generator.generate_concurrent_failure_scenarios()
        skipped_devices = set()
        
        for scenario in scenarios:
            device_type = scenario.primary_device.device_type
            if device_type in skipped_devices:
                continue
                
            with self.subTest(device=scenario.primary_device.name):
                try:
                    # Validate device availability
                    if not self.device_manager.validate_device(device_type):
                        logging.warning(f"Skipping concurrent failure tests for unavailable device type: {device_type.name}")
                        skipped_devices.add(device_type)
                        continue
                    
                    wasapi = WASAPIMonitor(self.coordinator)
                    
                    # Initialize stream
                    success = wasapi.initialize_stream(
                        device_index=scenario.primary_device.device_index
                    )
                    self.assertTrue(success)
                    
                    # Verify recovery from concurrent failures
                    recovery_success = await self.verify_recovery_success(scenario)
                    self.assertTrue(
                        recovery_success,
                        f"Failed to recover from concurrent failures on {scenario.primary_device.name}"
                    )
                    
                finally:
                    if 'wasapi' in locals():
                        wasapi.cleanup()
                        
        # Log summary of skipped devices
        if skipped_devices:
            logging.info(f"Skipped concurrent failure tests for unavailable devices: {[d.name for d in skipped_devices]}")

    async def test_cascading_failures(self):
        """Test scenarios with cascading failures.
        
        Verifies the system's ability to handle and recover from
        cascading failure scenarios. This test:
        1. Simulates cascading failures
        2. Tests recovery sequence
        3. Verifies system resilience
        4. Monitors recovery chain
        
        Test Sequence:
            1. Generate cascading scenarios
            2. Apply failure chain
            3. Monitor recovery steps
            4. Verify final state
            5. Check system health
        
        Expected Results:
            - Complete recovery chain
            - Proper error handling
            - System stability
            - Resource management
        
        Example Metrics:
            - Recovery chain length
            - Total recovery time
            - Resource impact
            - Error propagation
            
        Note:
            Tests will be skipped for device types that are not available
            on the current system.
        """
        scenarios = self.scenario_generator.generate_cascading_failure_scenarios()
        skipped_devices = set()
        
        for scenario in scenarios:
            device_type = scenario.primary_device.device_type
            if device_type in skipped_devices:
                continue
                
            with self.subTest(device=scenario.primary_device.name):
                try:
                    # Validate device availability
                    if not self.device_manager.validate_device(device_type):
                        logging.warning(f"Skipping cascading failure tests for unavailable device type: {device_type.name}")
                        skipped_devices.add(device_type)
                        continue
                    
                    wasapi = WASAPIMonitor(self.coordinator)
                    
                    # Initialize stream
                    success = wasapi.initialize_stream(
                        device_index=scenario.primary_device.device_index
                    )
                    self.assertTrue(success)
                    
                    # Verify recovery from cascading failures
                    recovery_success = await self.verify_recovery_success(scenario)
                    self.assertTrue(
                        recovery_success,
                        f"Failed to recover from cascading failures on {scenario.primary_device.name}"
                    )
                    
                finally:
                    if 'wasapi' in locals():
                        wasapi.cleanup()
                        
        # Log summary of skipped devices
        if skipped_devices:
            logging.info(f"Skipped cascading failure tests for unavailable devices: {[d.name for d in skipped_devices]}")

    async def test_random_scenarios(self):
        """Test random combinations of failure scenarios.
        
        Verifies the system's ability to handle unexpected and random
        combinations of failure scenarios. This test:
        1. Generates random scenarios
        2. Tests varied combinations
        3. Verifies recovery robustness
        4. Monitors system stability
        
        Test Sequence:
            1. Generate random scenarios
            2. Apply varied failures
            3. Monitor recovery process
            4. Verify system health
            5. Track performance
        
        Expected Results:
            - Successful recovery
            - System stability
            - Resource management
            - Error handling
        
        Example Metrics:
            - Scenario complexity
            - Recovery success rate
            - Performance impact
            - Resource utilization
            
        Note:
            Tests will be skipped for device types that are not available
            on the current system.
        """
        skipped_devices = set()
        
        # Test 10 random scenarios
        for scenario in self.scenario_generator.generate_scenario_sequence(count=10):
            device_type = scenario.primary_device.device_type
            if device_type in skipped_devices:
                continue
                
            with self.subTest(scenario_type=scenario.scenario_type):
                try:
                    # Validate device availability
                    if not self.device_manager.validate_device(device_type):
                        logging.warning(f"Skipping random scenario tests for unavailable device type: {device_type.name}")
                        skipped_devices.add(device_type)
                        continue
                    
                    wasapi = WASAPIMonitor(self.coordinator)
                    
                    # Initialize with scenario's primary device
                    success = wasapi.initialize_stream(
                        device_index=scenario.primary_device.device_index
                    )
                    self.assertTrue(success)
                    
                    # Verify recovery from random scenario
                    recovery_success = await self.verify_recovery_success(scenario)
                    self.assertTrue(
                        recovery_success,
                        f"Failed to recover from random scenario: {scenario.scenario_type}"
                    )
                    
                finally:
                    if 'wasapi' in locals():
                        wasapi.cleanup()
                        
        # Log summary of skipped devices
        if skipped_devices:
            logging.info(f"Skipped random scenario tests for unavailable devices: {[d.name for d in skipped_devices]}")

    async def test_comprehensive_suite(self):
        """Run comprehensive test suite with all scenario types and performance monitoring.
        
        Executes a complete test suite covering all failure scenarios
        while monitoring system performance. This test:
        1. Runs all scenario types
        2. Monitors overall performance
        3. Tracks resource usage
        4. Analyzes system stability
        
        Test Sequence:
            1. Generate complete suite
            2. Execute all scenarios
            3. Monitor performance
            4. Track resource usage
            5. Analyze results
        
        Expected Results:
            - All scenarios handled
            - Performance within limits
            - Resource management
            - Complete metrics
        
        Example Metrics:
            - Total recovery time
            - Max resource usage
            - Failed scenarios
            - Performance stats
            
        Note:
            Tests will be skipped for device types that are not available
            on the current system.
        """
        scenarios = create_test_suite(self.device_manager)
        skipped_devices = set()
        
        # Track overall performance
        suite_metrics = {
            'total_recovery_time': 0,
            'max_cpu_usage': 0,
            'max_memory_usage': 0,
            'max_buffer_usage': 0,
            'failed_scenarios': [],
            'skipped_scenarios': []
        }
        
        for scenario in scenarios:
            device_type = scenario.primary_device.device_type
            if device_type in skipped_devices:
                suite_metrics['skipped_scenarios'].append({
                    'scenario': scenario.scenario_type,
                    'device': device_type.name,
                    'reason': 'Device not available'
                })
                continue
                
            with self.subTest(scenario_type=scenario.scenario_type):
                # Clear performance metrics for this test
                for metric_list in self.performance_metrics.values():
                    metric_list.clear()
                
                try:
                    # Validate device availability
                    if not self.device_manager.validate_device(device_type):
                        logging.warning(f"Skipping comprehensive test for unavailable device type: {device_type.name}")
                        skipped_devices.add(device_type)
                        suite_metrics['skipped_scenarios'].append({
                            'scenario': scenario.scenario_type,
                            'device': device_type.name,
                            'reason': 'Device validation failed'
                        })
                        continue
                    
                    wasapi = WASAPIMonitor(self.coordinator)
                    start_time = time.perf_counter()
                    
                    # Initialize with scenario's primary device
                    success = wasapi.initialize_stream(
                        device_index=scenario.primary_device.device_index
                    )
                    self.assertTrue(success)
                    
                    # Verify recovery from scenario
                    recovery_success = await self.verify_recovery_success(scenario)
                    self.assertTrue(
                        recovery_success,
                        f"Failed to recover from {scenario.scenario_type}"
                    )
                    
                    # Update suite metrics
                    scenario_time = time.perf_counter() - start_time
                    suite_metrics['total_recovery_time'] += scenario_time
                    suite_metrics['max_cpu_usage'] = max(
                        suite_metrics['max_cpu_usage'],
                        max(self.performance_metrics['cpu_usage'])
                    )
                    suite_metrics['max_memory_usage'] = max(
                        suite_metrics['max_memory_usage'],
                        max(self.performance_metrics['memory_usage'])
                    )
                    suite_metrics['max_buffer_usage'] = max(
                        suite_metrics['max_buffer_usage'],
                        max(self.performance_metrics['buffer_usage'])
                    )
                    
                except Exception as e:
                    suite_metrics['failed_scenarios'].append({
                        'scenario': scenario.scenario_type,
                        'device': device_type.name,
                        'error': str(e),
                        'metrics': {
                            metric: statistics.mean(values) if values else 0
                            for metric, values in self.performance_metrics.items()
                        }
                    })
                    raise
                
                finally:
                    if 'wasapi' in locals():
                        wasapi.cleanup()
        
        # Log summary of skipped devices
        if skipped_devices:
            logging.info(f"Skipped comprehensive tests for unavailable devices: {[d.name for d in skipped_devices]}")
        
        # Log suite performance metrics
        self.recovery_logger.log_event('suite_performance', suite_metrics)

if __name__ == '__main__':
    import asyncio
    asyncio.run(unittest.main())
