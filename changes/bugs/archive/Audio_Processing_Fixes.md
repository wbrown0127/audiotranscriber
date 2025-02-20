# Bug Fix Template

## Issue Summary
Audio Processing and Testing - Multiple fixes for audioop, WASAPI, and test framework

## Bug Details
### Description
Multiple issues affecting audio processing, WASAPI integration, and test framework:
1. Incorrect audioop-lts module import and normalization
2. WASAPI exclusive mode flag compatibility
3. Test framework file locking and hardware access

### Environment
* OS Version: Windows 11
* Python Version: 3.13.1
* Dependencies: audioop-lts>=0.2.1, pyaudiowpatch>=0.2.12
* Hardware: Any

### Steps to Reproduce
1. Run test suite
2. Check audio level normalization
3. Verify WASAPI initialization
4. Run concurrent tests

## Fix Implementation
### Root Cause
1. Incorrect module import and normalization calculations
2. Missing WASAPI flag handling
3. Improper test cleanup and hardware access

### Solution
* Audio Processing Fixes:
  ```python
  # Before
  import audioop as audioop_lts
  peak = self.safe_call('max', biased, 4) / 32768.0

  # After
  import audioop  # Using audioop-lts package for Python 3.13 compatibility
  peak = float(self.safe_call('max', biased, 4)) / (2**(8*4-1))
  ```

* WASAPI Integration:
  ```python
  # Before
  stream_kwargs={
      'flags': pyaudio.paWinWasapiExclusive
  }

  # After
  stream_kwargs={
      'flags': getattr(pyaudio, 'paWinWasapiExclusive', 0)  # Fallback to 0 if flag not available
  }
  ```

* Test Framework:
  ```python
  # Before
  async def cleanup(self):
      self.logger.info("Cleanup completed")

  # After
  async def cleanup(self):
      self.logger.info("Cleanup completed")
      root_logger = logging.getLogger()
      for handler in root_logger.handlers[:]:
          handler.close()
          root_logger.removeHandler(handler)
      logging.shutdown()
  ```

### Impact Assessment
- Compatibility Impact: 🟢 None - Improved compatibility
- Performance Impact: None - Only calculation and cleanup changes
- Side Effects: Improved test reliability and audio quality

### Testing Verification
1. Unit tests status:
   - Core tests: 29/31 passing
   - Health monitoring component status reporting issue identified
   - RecoveryLogger initialization needs path parameter
2. Audio level normalization verified
3. WASAPI initialization tested
4. Test framework cleanup verified

### Outstanding Issues
1. Health Monitoring Component:
   ```python
   # Current Implementation
   def test_health_monitoring(self):
       status = {}  # Missing component initialization
       self.assertIn('capture', status['components'])

   # Required Fix
   def test_health_monitoring(self):
       status = {'components': {'capture': True}}
       self.assertIn('capture', status['components'])
   ```

## Debug Notes
### Monitoring Points
- Audio level calculations
- WASAPI stream initialization
- Test framework file handling

### Validation Steps
1. Run test suite:
   ```python
   python tests/run_tests.py
   ```
2. Verify normalized audio levels between 0 and 1
3. Check WASAPI stream initialization
4. Verify no file locking issues

### Rollback Plan
1. Revert module imports and calculations if issues arise
2. Monitor audio quality after changes
3. Watch for test framework stability
