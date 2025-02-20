"""
Recovery scenario generator for audio device testing.
Generates test scenarios for various failure and recovery cases.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Generator, Set
import random
import time
import logging
from enum import Enum, auto
from .device_config import DeviceConfig, DeviceType, DeviceManager, DeviceSimulator

class ScenarioType(Enum):
    """Types of test scenarios."""
    DEVICE_FAILURE = auto()
    BUFFER_UNDERRUN = auto()
    FORMAT_MISMATCH = auto()
    DEVICE_SWITCH = auto()
    CONCURRENT_FAILURE = auto()
    CASCADING_FAILURE = auto()

@dataclass
class ScenarioConfig:
    """Represents a test scenario configuration."""
    scenario_type: ScenarioType
    primary_device: DeviceConfig
    secondary_device: Optional[DeviceConfig] = None
    duration: float = 1.0
    expected_recovery_time: float = 0.5
    error_sequence: List[Dict] = None
    
    def validate(self) -> bool:
        """Validate scenario configuration."""
        try:
            assert self.duration > 0, "Duration must be positive"
            assert self.expected_recovery_time > 0, "Recovery time must be positive"
            assert self.expected_recovery_time < self.duration, "Recovery time must be less than duration"
            assert self.error_sequence is not None, "Error sequence is required"
            
            # Validate error sequence
            for error in self.error_sequence:
                assert 'error_type' in error, "Error type is required"
                assert 'timestamp' in error, "Timestamp is required"
                if error['error_type'] == 'device_switch':
                    assert self.secondary_device is not None, "Secondary device required for device switch"
                    assert 'old_device' in error and 'new_device' in error, "Device switch requires old and new device info"
            
            # Validate timing between errors
            if len(self.error_sequence) > 1:
                for i in range(len(self.error_sequence) - 1):
                    time_diff = self.error_sequence[i + 1]['timestamp'] - self.error_sequence[i]['timestamp']
                    assert time_diff >= 0.1, "Errors must be at least 100ms apart"
            
            return True
        except AssertionError as e:
            logging.error(f"Scenario validation failed: {e}")
            return False

class ScenarioGenerator:
    """Generates test scenarios for audio device testing."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager
        self.simulator = DeviceSimulator()
        self.logger = logging.getLogger('scenario_generator')
        
    def calculate_duration(self, scenario_type: ScenarioType, error_count: int) -> float:
        """Calculate appropriate duration based on scenario type and complexity."""
        base_duration = {
            ScenarioType.DEVICE_FAILURE: 2.0,
            ScenarioType.BUFFER_UNDERRUN: 1.5,
            ScenarioType.FORMAT_MISMATCH: 1.5,
            ScenarioType.DEVICE_SWITCH: 3.0,
            ScenarioType.CONCURRENT_FAILURE: 4.0,
            ScenarioType.CASCADING_FAILURE: 5.0
        }
        return base_duration[scenario_type] * (1 + 0.5 * (error_count - 1))

    def estimate_recovery_time(self, scenario_type: ScenarioType, error_count: int) -> float:
        """Estimate recovery time based on scenario type and number of errors."""
        base_recovery = {
            ScenarioType.DEVICE_FAILURE: 1.0,
            ScenarioType.BUFFER_UNDERRUN: 0.5,
            ScenarioType.FORMAT_MISMATCH: 0.75,
            ScenarioType.DEVICE_SWITCH: 1.5,
            ScenarioType.CONCURRENT_FAILURE: 2.0,
            ScenarioType.CASCADING_FAILURE: 2.5
        }
        return base_recovery[scenario_type] * (1 + 0.3 * (error_count - 1))

    def validate_device_compatibility(self, primary: DeviceConfig, 
                                   secondary: Optional[DeviceConfig] = None) -> bool:
        """Validate device compatibility for testing."""
        try:
            # Validate primary device
            if not self.device_manager.validate_device(primary.device_type):
                self.logger.error(f"Primary device {primary.name} validation failed")
                return False
            
            # Validate secondary device if provided
            if secondary and not self.device_manager.validate_device(secondary.device_type):
                self.logger.error(f"Secondary device {secondary.name} validation failed")
                return False
            
            # Check format compatibility for device switch
            if secondary:
                if primary.format != secondary.format:
                    self.logger.error("Format mismatch between devices")
                    return False
                if primary.channels != secondary.channels:
                    self.logger.error("Channel count mismatch between devices")
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"Device compatibility check failed: {e}")
            return False

    def generate_basic_scenarios(self) -> List[ScenarioConfig]:
        """Generate basic test scenarios for each device."""
        scenarios = []
        
        for device_type in DeviceType:
            try:
                device_config = self.device_manager.get_config(device_type)
                if not self.validate_device_compatibility(device_config):
                    continue
                
                # Device failure scenario
                duration = self.calculate_duration(ScenarioType.DEVICE_FAILURE, 1)
                recovery_time = self.estimate_recovery_time(ScenarioType.DEVICE_FAILURE, 1)
                scenarios.append(ScenarioConfig(
                    scenario_type=ScenarioType.DEVICE_FAILURE,
                    primary_device=device_config,
                    duration=duration,
                    expected_recovery_time=recovery_time,
                    error_sequence=[
                        self.simulator.simulate_device_failure(device_config)
                    ]
                ))
                
                # Buffer underrun scenario
                duration = self.calculate_duration(ScenarioType.BUFFER_UNDERRUN, 1)
                recovery_time = self.estimate_recovery_time(ScenarioType.BUFFER_UNDERRUN, 1)
                scenarios.append(ScenarioConfig(
                    scenario_type=ScenarioType.BUFFER_UNDERRUN,
                    primary_device=device_config,
                    duration=duration,
                    expected_recovery_time=recovery_time,
                    error_sequence=[
                        self.simulator.simulate_buffer_underrun(device_config)
                    ]
                ))
                
                # Format mismatch scenario
                duration = self.calculate_duration(ScenarioType.FORMAT_MISMATCH, 1)
                recovery_time = self.estimate_recovery_time(ScenarioType.FORMAT_MISMATCH, 1)
                scenarios.append(ScenarioConfig(
                    scenario_type=ScenarioType.FORMAT_MISMATCH,
                    primary_device=device_config,
                    duration=duration,
                    expected_recovery_time=recovery_time,
                    error_sequence=[
                        self.simulator.simulate_format_mismatch(device_config)
                    ]
                ))
            except ValueError as e:
                self.logger.warning(f"Skipping device {device_type}: {e}")
                continue
                
        return [s for s in scenarios if s.validate()]

    def generate_device_switch_scenarios(self) -> List[ScenarioConfig]:
        """Generate scenarios for switching between devices."""
        scenarios = []
        configs = self.device_manager.get_all_configs()
        
        for i, primary in enumerate(configs):
            for secondary in configs[i+1:]:
                if not self.validate_device_compatibility(primary, secondary):
                    continue
                    
                duration = self.calculate_duration(ScenarioType.DEVICE_SWITCH, 1)
                recovery_time = self.estimate_recovery_time(ScenarioType.DEVICE_SWITCH, 1)
                
                scenarios.append(ScenarioConfig(
                    scenario_type=ScenarioType.DEVICE_SWITCH,
                    primary_device=primary,
                    secondary_device=secondary,
                    duration=duration,
                    expected_recovery_time=recovery_time,
                    error_sequence=[
                        self.simulator.simulate_device_switch(primary, secondary)
                    ]
                ))
                
        return [s for s in scenarios if s.validate()]

    def generate_concurrent_failure_scenarios(self) -> List[ScenarioConfig]:
        """Generate scenarios with multiple simultaneous failures."""
        scenarios = []
        configs = self.device_manager.get_all_configs()
        
        for primary in configs:
            if not self.validate_device_compatibility(primary):
                continue
                
            # Concurrent buffer underrun and device failure
            duration = self.calculate_duration(ScenarioType.CONCURRENT_FAILURE, 2)
            recovery_time = self.estimate_recovery_time(ScenarioType.CONCURRENT_FAILURE, 2)
            base_time = time.time()
            
            scenarios.append(ScenarioConfig(
                scenario_type=ScenarioType.CONCURRENT_FAILURE,
                primary_device=primary,
                duration=duration,
                expected_recovery_time=recovery_time,
                error_sequence=[
                    {**self.simulator.simulate_buffer_underrun(primary), 'timestamp': base_time},
                    {**self.simulator.simulate_device_failure(primary), 'timestamp': base_time + 0.1}
                ]
            ))
            
        return [s for s in scenarios if s.validate()]

    def generate_cascading_failure_scenarios(self) -> List[ScenarioConfig]:
        """Generate scenarios with cascading failures."""
        scenarios = []
        configs = self.device_manager.get_all_configs()
        
        for primary in configs:
            if not self.validate_device_compatibility(primary):
                continue
                
            # Cascading failure: buffer underrun -> format mismatch -> device failure
            duration = self.calculate_duration(ScenarioType.CASCADING_FAILURE, 3)
            recovery_time = self.estimate_recovery_time(ScenarioType.CASCADING_FAILURE, 3)
            base_time = time.time()
            
            scenarios.append(ScenarioConfig(
                scenario_type=ScenarioType.CASCADING_FAILURE,
                primary_device=primary,
                duration=duration,
                expected_recovery_time=recovery_time,
                error_sequence=[
                    {**self.simulator.simulate_buffer_underrun(primary), 'timestamp': base_time},
                    {**self.simulator.simulate_format_mismatch(primary), 'timestamp': base_time + 0.5},
                    {**self.simulator.simulate_device_failure(primary), 'timestamp': base_time + 1.0}
                ]
            ))
            
        return [s for s in scenarios if s.validate()]

    def generate_random_scenario(self) -> Optional[ScenarioConfig]:
        """Generate a random test scenario with validation."""
        try:
            scenario_type = random.choice(list(ScenarioType))
            configs = self.device_manager.get_all_configs()
            
            if not configs:
                self.logger.error("No valid device configurations available")
                return None
                
            primary = random.choice(configs)
            if not self.validate_device_compatibility(primary):
                self.logger.error(f"Primary device {primary.name} validation failed")
                return None
            
            if scenario_type == ScenarioType.DEVICE_SWITCH:
                remaining = [c for c in configs if c != primary]
                if remaining:
                    secondary = random.choice(remaining)
                    if not self.validate_device_compatibility(primary, secondary):
                        return None
                        
                    duration = self.calculate_duration(scenario_type, 1)
                    recovery_time = self.estimate_recovery_time(scenario_type, 1)
                    
                    scenario = ScenarioConfig(
                        scenario_type=scenario_type,
                        primary_device=primary,
                        secondary_device=secondary,
                        duration=duration,
                        expected_recovery_time=recovery_time,
                        error_sequence=[
                            self.simulator.simulate_device_switch(primary, secondary)
                        ]
                    )
                    return scenario if scenario.validate() else None
            
            error_funcs = [
                self.simulator.simulate_device_failure,
                self.simulator.simulate_buffer_underrun,
                self.simulator.simulate_format_mismatch
            ]
            
            error_count = 1
            if scenario_type in [ScenarioType.CONCURRENT_FAILURE, ScenarioType.CASCADING_FAILURE]:
                error_count = random.randint(2, 3)
            
            duration = self.calculate_duration(scenario_type, error_count)
            recovery_time = self.estimate_recovery_time(scenario_type, error_count)
            base_time = time.time()
            
            error_sequence = []
            for i in range(error_count):
                error = random.choice(error_funcs)(primary)
                error['timestamp'] = base_time + (0.1 if scenario_type == ScenarioType.CONCURRENT_FAILURE else 0.5 * i)
                error_sequence.append(error)
            
            scenario = ScenarioConfig(
                scenario_type=scenario_type,
                primary_device=primary,
                duration=duration,
                expected_recovery_time=recovery_time,
                error_sequence=error_sequence
            )
            return scenario if scenario.validate() else None
            
        except Exception as e:
            self.logger.error(f"Error generating random scenario: {e}")
            return None

    def generate_scenario_sequence(self, count: int = 10) -> Generator[ScenarioConfig, None, None]:
        """Generate a sequence of validated test scenarios."""
        generated = 0
        attempts = 0
        max_attempts = count * 3  # Allow up to 3 attempts per requested scenario
        
        while generated < count and attempts < max_attempts:
            scenario = self.generate_random_scenario()
            attempts += 1
            
            if scenario:
                generated += 1
                yield scenario

def create_test_suite(device_manager: DeviceManager) -> List[ScenarioConfig]:
    """Create a comprehensive test suite with validated scenarios."""
    generator = ScenarioGenerator(device_manager)
    scenarios = []
    
    # Collect all scenarios
    scenarios.extend(generator.generate_basic_scenarios())
    scenarios.extend(generator.generate_device_switch_scenarios())
    scenarios.extend(generator.generate_concurrent_failure_scenarios())
    scenarios.extend(generator.generate_cascading_failure_scenarios())
    
    # Log scenario statistics
    scenario_counts = {}
    for scenario in scenarios:
        scenario_counts[scenario.scenario_type] = scenario_counts.get(scenario.scenario_type, 0) + 1
    
    for scenario_type, count in scenario_counts.items():
        logging.info(f"Generated {count} {scenario_type.name} scenarios")
    
    return scenarios
