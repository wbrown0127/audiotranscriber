# Audio Capture and Device Handling Issues

## Issue Summary
Critical issues affecting audio capture, device management, and stream handling.

## Bug Details
### Description
Several critical issues identified in audio capture system:

1. Stream Management Issues:
- No proper stream state recovery
- Missing device capability validation
- Incomplete stream cleanup
- Buffer size adjustment race conditions

2. Device Handling Issues:
- Hardcoded device indices
- Missing device fallback mechanism
- Incomplete device capability checks
- No device hot-plug support

3. Performance Monitoring Issues:
- Uncoordinated buffer size adjustments
- Missing performance history
- Incomplete channel health metrics
- No adaptive thresholds

4. Channel Management Issues:
- Channel synchronization problems
- Missing channel-specific health checks
- Incomplete buffer management
- No channel recovery mechanism

### Environment
* OS: Windows 11
* Python: 3.13.1
* Dependencies:
  - pyaudiowpatch
  - numpy
  - psutil
* Components Affected:
  - AdaptiveAudioCapture
  - PerformanceMonitor
  - WASAPI integration
  - Buffer management

### Root Causes
1. Stream Management:
   ```python
   # Current - Basic stream initialization
   def initialize_stream(self, device_index: Optional[int] = None) -> bool:
       try:
           if not self.pa:
               self.pa = pyaudio.PyAudio()
           self.stream = self.pa.open(
               format=pyaudio.paFloat32,
               channels=2,
               rate=int(device_info['defaultSampleRate']),
               input=True
           )
           
   # Needs
   def initialize_stream(self, device_index: Optional[int] = None) -> bool:
       try:
           if not self.pa:
               self.pa = pyaudio.PyAudio()
               
           # Validate device capabilities
           device_info = self._validate_device(device_index)
           if not device_info['valid']:
               return self._try_fallback_device()
               
           # Configure with device-specific settings
           config = self._get_device_config(device_info)
           self.stream = await self._create_stream_with_retry(config)
           
           return await self._verify_stream_health()
   ```

2. Performance Monitoring:
   ```python
   # Current - Simple monitoring
   def get_cpu_stats(self) -> tuple[float, Optional[float]]:
       cpu_usage = psutil.cpu_percent(interval=1)
       try:
           temp = psutil.sensors_temperatures()['coretemp'][0].current
       except (AttributeError, KeyError):
           temp = None
       return cpu_usage, temp
       
   # Needs
   def get_performance_metrics(self) -> Dict[str, Any]:
       metrics = {
           'cpu': self._get_cpu_metrics(),
           'memory': self._get_memory_metrics(),
           'temperature': self._get_temperature_metrics(),
           'audio': self._get_audio_metrics()
       }
       
       self._update_history(metrics)
       self._check_thresholds(metrics)
       
       return metrics
   ```

3. Channel Management:
   ```python
   # Current - Basic channel verification
   def _verify_channel_health(self, left: np.ndarray, right: np.ndarray) -> dict:
       issues = []
       if np.any(np.isnan(left)) or np.any(np.isnan(right)):
           issues.append("NaN values detected")
       return {'healthy': len(issues) == 0, 'issues': issues}
       
   # Needs
   def _verify_channel_health(self, left: np.ndarray, right: np.ndarray) -> dict:
       analysis = {
           'left': self._analyze_channel(left),
           'right': self._analyze_channel(right),
           'correlation': self._analyze_correlation(left, right)
       }
       
       health_status = self._evaluate_channel_health(analysis)
       if not health_status['healthy']:
           await self._handle_channel_issues(health_status['issues'])
           
       return health_status
   ```

4. Buffer Management:
   ```python
   # Current - Direct buffer updates
   def _stream_callback(self, in_data, frame_count, time_info, status):
       audio_data = np.frombuffer(in_data, dtype=np.float32)
       left_channel = audio_data[::2]
       right_channel = audio_data[1::2]
       
   # Needs
   def _stream_callback(self, in_data, frame_count, time_info, status):
       try:
           with self.coordinator.capture_lock():
               # Validate input data
               if not self._validate_input_data(in_data, frame_count):
                   return self._handle_invalid_data()
                   
               # Process channels atomically
               channels = self._split_channels(in_data)
               if not self._validate_channels(channels):
                   return self._handle_channel_error()
                   
               # Update buffers with rollback support
               if not await self._update_channel_buffers(channels):
                   return self._handle_buffer_error()
                   
               return (in_data, pyaudio.paContinue)
       except Exception as e:
           return self._handle_callback_error(e)
   ```

## Impact Assessment
- Reliability Impact: 🔴 High - Audio capture stability
- Performance Impact: 🔴 High - Buffer management issues
- Quality Impact: 🔴 High - Audio data integrity

## Testing Verification
1. Stream Management:
   - Stream initialization: Issues present
   - Device validation: Incomplete
   - Recovery handling: Missing
   - Cleanup: Issues present

2. Performance Monitoring:
   - CPU monitoring: Working
   - Memory tracking: Incomplete
   - Temperature monitoring: Issues present
   - Buffer management: Issues present

3. Channel Management:
   - Channel health: Incomplete
   - Synchronization: Issues present
   - Recovery: Missing
   - Buffer handling: Issues present

## Debug Notes
### Required Changes
1. Stream Management:
   - Add device validation
   - Implement fallback system
   - Add recovery mechanism
   - Improve cleanup

2. Performance Monitoring:
   - Add comprehensive metrics
   - Implement history tracking
   - Add threshold management
   - Improve coordination

3. Channel Management:
   - Add channel validation
   - Implement synchronization
   - Add recovery procedures
   - Improve buffer handling

4. Error Handling:
   - Add error categorization
   - Implement recovery steps
   - Add error tracking
   - Improve reporting

### Validation Steps
1. Stream Management:
   ```python
   def validate_stream():
       capture = AdaptiveAudioCapture(coordinator)
       
       # Test initialization
       assert capture.initialize_stream()
       assert capture.stream.is_active()
       
       # Test device validation
       with invalid_device():
           assert not capture.initialize_stream()
           assert capture._try_fallback_device()
           
       # Test cleanup
       capture.stop_capture()
       assert not capture.stream
       assert not capture.pa
   ```

2. Performance Monitoring:
   ```python
   def validate_performance():
       monitor = PerformanceMonitor()
       
       # Test metrics
       metrics = monitor.get_performance_metrics()
       assert all(k in metrics for k in 
                 ['cpu', 'memory', 'temperature', 'audio'])
       
       # Test history
       assert len(monitor.get_metric_history('cpu')) > 0
       
       # Test thresholds
       with high_cpu_load():
           assert monitor.should_adjust(metrics)
   ```

3. Channel Management:
   ```python
   def validate_channels():
       capture = AdaptiveAudioCapture(coordinator)
       
       # Test channel health
       data = get_test_audio()
       health = capture._verify_channel_health(
           data['left'], data['right']
       )
       assert health['healthy']
       
       # Test recovery
       with simulated_channel_error():
           health = capture._verify_channel_health(
               data['left'], data['right']
           )
           assert not health['healthy']
           assert capture._handle_channel_issues(health['issues'])
   ```

### Rollback Plan
1. Stream Management:
   - Keep current initialization
   - Add basic validation
   - Phase in recovery
   - Maintain compatibility

2. Performance Monitoring:
   - Keep current metrics
   - Add basic history
   - Phase in thresholds
   - Keep current coordination

3. Channel Management:
   - Keep current validation
   - Add basic recovery
   - Phase in synchronization
   - Maintain buffer handling
