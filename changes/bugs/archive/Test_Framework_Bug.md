# Test Framework and Device Testing Issues

## Issue Summary
Multiple issues affecting test reliability, device handling, and scenario generation.

## Bug Details
### Description
Several critical issues identified in test framework and device testing:

1. Device Testing Issues:
- Device initialization not properly handling missing hardware
- Hardcoded device indices (31 for system loopback, 29 for VB-Cable)
- No fallback for missing test devices
- Device simulation may not match real hardware behavior

2. Test Scenario Issues:
- Random scenario generation may create unrealistic test cases
- Cascading failure scenarios have fixed timing assumptions
- No validation of device compatibility before scenario generation
- Error sequences may not match real-world patterns

3. Test Configuration Issues:
- Test config files in wrong location (src/audio_transcriber/test_config)
- Device manager cleanup not properly integrated with test lifecycle
- Missing error handling for device initialization failures
- No configuration for test device requirements

4. Test Timing Issues:
- Fixed duration and recovery time expectations
- No adaptation to system performance
- Concurrent failure timing not properly coordinated
- Recovery time assumptions may be too optimistic

### Environment
* OS: Windows 11
* Python: 3.13.1
* Components Affected:
  - DeviceManager
  - ScenarioGenerator
  - TestReport
  - pytest configuration
  - test utilities

### Root Causes
1. Device Configuration:
   ```python
   # Current - Hardcoded indices
   self.system_loopback_device = 31  # Speakers (Realtek) [Loopback]
   self.vb_cable_device = 29         # CABLE Output
   
   # Needs
   def find_device_by_name(self, name_pattern: str) -> Optional[int]:
       for i in range(self.pa.get_device_count()):
           info = self.pa.get_device_info_by_index(i)
           if name_pattern.lower() in info['name'].lower():
               return i
       return None
   ```

2. Test Scenarios:
   ```python
   # Current - Fixed timing
   duration=3.0,
   expected_recovery_time=1.5,
   
   # Needs
   duration=self.calculate_duration_for_scenario(scenario_type),
   expected_recovery_time=self.estimate_recovery_time(error_sequence)
   ```

3. Device Manager:
   ```python
   # Current - No proper cleanup
   def cleanup(self):
       if hasattr(self, 'pa'):
           self.pa.terminate()
           
   # Needs
   def cleanup(self):
       try:
           if hasattr(self, 'pa'):
               for stream in self.active_streams:
                   stream.stop_stream()
                   stream.close()
               self.pa.terminate()
       except Exception as e:
           logging.error(f"Cleanup failed: {e}")
   ```

4. Test Configuration:
   ```python
   # Current - No device requirements
   class TestWASAPIStability(unittest.TestCase):
       def setUp(self):
           self.device_manager = DeviceManager()
           
   # Needs
   @pytest.mark.requires_devices(['loopback', 'vb_cable'])
   class TestWASAPIStability(unittest.TestCase):
       def setUp(self):
           self.device_manager = DeviceManager()
           self.verify_required_devices()
   ```

## Impact Assessment
- Compatibility Impact: 🔴 High - Tests may fail on different hardware
- Reliability Impact: 🔴 High - Inconsistent test results
- Maintenance Impact: 🟡 Medium - Test maintenance difficulties

## Testing Verification
1. Device Tests:
   - Hardware detection: Failing
   - Device simulation: Partially working
   - Recovery scenarios: Unreliable

2. Test Framework:
   - Configuration loading: Working
   - Scenario generation: Partially working
   - Result reporting: Working

3. Integration Tests:
   - Device switching: Failing
   - Concurrent failures: Unreliable
   - Recovery timing: Inconsistent

## Debug Notes
### Required Changes
1. Device Management:
   - Implement dynamic device detection
   - Add device capability verification
   - Improve cleanup handling
   - Add fallback configurations

2. Test Framework:
   - Move test_config to correct location
   - Implement device requirement decorators
   - Add scenario validation
   - Improve timing handling

3. Test Scenarios:
   - Add realistic timing calculations
   - Validate device compatibility
   - Improve error sequence generation
   - Add scenario verification

4. Test Configuration:
   - Add device requirement configuration
   - Implement test skip logic
   - Add hardware verification
   - Improve error reporting

### Validation Steps
1. Device Detection:
   ```python
   def verify_devices():
       manager = DeviceManager()
       devices = manager.get_all_configs()
       assert any(d.is_loopback for d in devices)
       assert any('cable' in d.name.lower() for d in devices)
   ```

2. Scenario Validation:
   ```python
   def validate_scenario(scenario: TestScenario):
       assert scenario.duration > 0
       assert scenario.expected_recovery_time > 0
       assert scenario.expected_recovery_time < scenario.duration
       for error in scenario.error_sequence:
           assert error['error_type'] in VALID_ERROR_TYPES
   ```

3. Timing Verification:
   ```python
   def verify_timing(scenario: TestScenario):
       start_time = time.time()
       run_scenario(scenario)
       duration = time.time() - start_time
       assert abs(duration - scenario.duration) < TIMING_TOLERANCE
   ```

### Rollback Plan
1. Device Configuration:
   - Store current device indices
   - Implement gradual migration
   - Add compatibility layer

2. Test Framework:
   - Keep old test location
   - Add symlinks for transition
   - Update imports gradually

3. Timing Handling:
   - Add configurable timeouts
   - Implement retry mechanism
   - Store timing statistics
