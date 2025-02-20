# Performance Tuning Guide

## Overview
This guide provides detailed information on optimizing the Audio Transcriber system's performance, including configuration recommendations, monitoring strategies, and troubleshooting procedures.

## 1. System Requirements

### Hardware Requirements
| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|--------|
| CPU | i5-8250U | i7-4790K | AVX2 support required |
| RAM | 4GB DDR4 | 8GB DDR4 | 2GB reserved for buffers |
| Storage | 100MB SATA | 100MB NVMe | For temporary files |
| Audio | VB-Cable | VB-Cable + Hardware | Free version sufficient |

### Software Requirements
- Windows 10 22H2 or later
- Python 3.13 or later
- pyaudiowpatch with WASAPI support
- audioop-lts library

## 2. Performance Thresholds

### CPU Management
```
Maximum CPU Usage: 80%
Temperature Limit: 85°C
Buffer Size Range: 30ms - 128ms
Core Allocation: Dynamic
```

### Memory Management
```
Process Limit: 100MB
GC Strategy: Dynamic optimization
Buffer Pool: 2GB maximum
Cleanup Trigger: Memory pressure or CPU load
```

### Storage Performance
```
Write Size: 32KB optimal
Buffer Threshold: 80%
Flush Interval: 1 second
Emergency Mode: Direct writes
```

## 3. Configuration Optimization

### Audio Capture
```python
# Optimal WASAPI Configuration
WASAPI_CONFIG = {
    'format': pyaudio.paFloat32,
    'channels': 2,
    'rate': 16000,
    'frames_per_buffer': 512,  # ~32ms at 16kHz
    'input_device_index': None,  # Auto-select
    'stream_callback': None,  # Use blocking mode
}

# Buffer Management
BUFFER_CONFIG = {
    'max_size': 1024 * 1024,  # 1MB
    'chunk_size': 32 * 1024,  # 32KB
    'prealloc': True,
    'emergency_size': 5 * 1024 * 1024  # 5MB
}
```

### Performance Monitoring
```python
# Monitoring Thresholds
MONITOR_CONFIG = {
    'cpu_threshold': 80.0,
    'memory_threshold': 100 * 1024 * 1024,  # 100MB
    'buffer_threshold': 0.8,  # 80%
    'check_interval': 1.0,  # 1 second
    'recovery_timeout': 0.5  # 500ms
}
```

## 4. Performance Monitoring

### Real-time Metrics
- CPU Usage
  * Per-core utilization
  * System temperature
  * Process priority

- Memory Usage
  * Process memory
  * Buffer allocation
  * GC statistics

- I/O Performance
  * Write latency
  * Buffer health
  * Storage capacity

### Monitoring Commands
```bash
# Check system health
python tests/verify_system_restart.py

# Run performance tests
python tests/run_tests.py --stability

# Monitor real-time metrics
python tests/test_real_devices.py
```

## 5. Performance Optimization

### CPU Optimization
1. Process Priority
   ```python
   # Set process priority
   import win32api, win32process, win32con
   handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
   win32process.SetPriorityClass(handle, win32process.HIGH_PRIORITY_CLASS)
   ```

2. Thread Affinity
   ```python
   # Set thread affinity
   import psutil
   p = psutil.Process()
   p.cpu_affinity([0, 1])  # Use first two cores
   ```

3. Buffer Optimization
   ```python
   # Dynamic buffer sizing
   def adjust_buffer_size(cpu_usage):
       if cpu_usage > 80:
           return 90  # 90ms buffer
       return 30  # 30ms buffer
   ```

### Memory Optimization
1. Buffer Pool
   ```python
   # Configure buffer pool
   from buffer_manager import BufferManager
   
   manager = BufferManager(
       pool_size=2 * 1024 * 1024 * 1024,  # 2GB
       chunk_size=32 * 1024,  # 32KB
       prealloc=True
   )
   ```

2. GC Configuration
   ```python
   # Configure garbage collection
   import gc
   
   gc.set_threshold(100000, 10, 10)
   gc.enable()
   ```

### I/O Optimization
1. Write Strategy
   ```python
   # Optimize write operations
   from storage_manager import StorageManager
   
   manager = StorageManager(
       buffer_size=32 * 1024,  # 32KB optimal write
       flush_interval=1.0,     # 1-second flush
       async_write=True
   )
   ```

2. Emergency Handling
   ```python
   # Configure emergency storage
   manager.configure_emergency({
       'mode': 'direct_write',
       'backup_path': 'emergency_backup',
       'max_size': 100 * 1024 * 1024  # 100MB
   })
   ```

## 6. Recovery Optimization

### Recovery Configuration
```python
# Configure recovery system
RECOVERY_CONFIG = {
    'max_attempts': 3,
    'stabilization_delay': 0.5,
    'timeout': 5.0,
    'fallback_mode': True
}
```

### Recovery Strategies
1. Stream Recovery
   - Maximum 3 attempts
   - 500ms stabilization
   - Fallback device support

2. Storage Recovery
   - Direct write mode
   - Temporary backup
   - Buffer preservation

3. State Recovery
   - State validation
   - Rollback support
   - History tracking

## 7. Troubleshooting

### Common Issues
1. High CPU Usage
   - Check process priority
   - Verify buffer sizes
   - Monitor thread allocation

2. Memory Leaks
   - Check buffer pool
   - Verify GC settings
   - Monitor object lifecycle

3. I/O Bottlenecks
   - Verify write sizes
   - Check async operations
   - Monitor buffer health

### Performance Testing
```bash
# Run comprehensive tests
python tests/run_tests.py --all

# Check specific component
python tests/test_stability.py

# Verify system state
python tests/verify_system_restart.py
```

## 8. Monitoring Dashboard

### Metrics Collection
- Real-time CPU usage
- Memory allocation
- I/O performance
- Buffer health
- Recovery statistics

### Alert Thresholds
- CPU: 80% sustained
- Memory: 100MB per process
- Buffer: 80% capacity
- Recovery: 3 failures

### Performance Reports
- Daily statistics
- Trend analysis
- Resource usage
- Recovery patterns

## 9. Best Practices

### Development
1. Regular monitoring
2. Performance testing
3. Resource optimization
4. Error handling

### Deployment
1. System verification
2. Configuration validation
3. Resource allocation
4. Monitoring setup

### Maintenance
1. Regular cleanup
2. Performance audits
3. Configuration updates
4. System optimization
