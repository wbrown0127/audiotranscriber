# Real-time Transcription Display System

## Overview
The transcription display system provides real-time visualization of multi-channel audio transcriptions with speaker identification, timestamp tracking, and performance optimization.

## Architecture

### Core Components

#### TranscriptionFormatter
- Manages real-time transcription formatting and display
- Handles speaker identification and channel mapping
- Implements confidence-based filtering
- Provides timestamp-based history management

```python
@dataclass
class TranscriptionSegment:
    speaker: str
    channel: int
    timestamp: float
    text: str
    confidence: float
```

### Data Flow
1. Audio Capture
   - WASAPI monitor captures stereo audio
   - Channels are separated and buffered
   - Each channel maps to a specific speaker

2. Transcription Processing
   - Audio chunks are transcribed via Whisper API
   - Confidence scores determine display filtering
   - Timestamps are synchronized with audio capture

3. Display Formatting
   - Segments formatted as: {Speaker - Channel - Timestamp "Text"}
   - Real-time display with < 100ms latency
   - History management with 30-second window

## Implementation Details

### Speaker Management
```python
# Register speakers for channels
formatter.register_speaker(0, "Agent")
formatter.register_speaker(1, "Customer")

# Speaker tracking automatically maps transcriptions
formatter.add_transcription(0, "Hello, how can I help?", 0.95)
# Output: {Agent - Channel 0 - 00:00:01 "Hello, how can I help?"}
```

### Confidence Filtering
- Default threshold: 0.7 (configurable)
- Filters out low-confidence transcriptions
- Prevents display of uncertain segments
- Maintains transcription quality

### History Management
- Rolling 30-second window
- Timestamp-based segment tracking
- Memory-efficient storage
- Real-time access to recent history

### Performance Optimization
- Immediate display with print buffering
- Efficient string formatting
- Minimal memory footprint
- Thread-safe operations

## Integration

### MonitoringCoordinator Integration
```python
# State updates for monitoring
coordinator.update_state(
    last_transcription=formatted_text,
    transcription_confidence=confidence
)

# Performance tracking
coordinator.update_performance_stats(
    'transcription_formatter',
    stats
)
```

### Buffer Management
- Channel-specific buffers
- Real-time synchronization
- Memory-efficient storage
- Automatic cleanup

## Performance Characteristics

### Latency Targets
- Display latency: < 100ms
- History access: < 10ms
- State updates: < 5ms
- Memory usage: < 100MB

### Resource Usage
- CPU: Minimal (string operations only)
- Memory: Linear with history window
- I/O: Print operations only
- Thread safety: Full coordination

## Testing

### Unit Tests
- Component-level functionality
- Format verification
- Confidence filtering
- History management

### Integration Tests
- End-to-end flow testing
- Performance validation
- Resource usage monitoring
- Long-term stability

## Error Handling

### Recovery Mechanisms
1. Invalid timestamps
   - Use current time as fallback
   - Log warning for investigation
   - Continue operation

2. Memory pressure
   - Reduce history window
   - Clear old segments
   - Maintain recent data

3. Display failures
   - Retry with backoff
   - Log errors
   - Maintain state

## Configuration

### Default Settings
```python
class TranscriptionFormatter:
    min_confidence = 0.7  # Confidence threshold
    history_window = 30.0  # Seconds
```

### System Requirements
- Python 3.13 or later
- Real-time display capability
- Memory for history buffer

### Performance Tuning
- Adjust confidence threshold for quality/quantity balance
- Modify history window for memory usage
- Configure buffer sizes for performance

## Monitoring

### Performance Metrics
- Display latency
- Memory usage
- Segment counts
- Speaker statistics

### Health Checks
- Buffer utilization
- Display responsiveness
- Memory pressure
- Error rates

## Best Practices

### Usage Guidelines
1. Register speakers before transcription
2. Monitor confidence scores
3. Check performance metrics
4. Handle cleanup properly

### Integration Guidelines
1. Use coordinator for state management
2. Monitor resource usage
3. Implement proper error handling
4. Follow cleanup protocols

## Known Issues

### Current Limitations
1. Fixed history window
   - Cannot be changed at runtime
   - Memory usage scales linearly

2. Print buffering
   - May delay display in high load
   - Consider async display in future

3. Timestamp precision
   - Limited to second resolution
   - Subsecond timing not displayed

### Phase 3 Considerations

1. Performance Management
   - CPU load from Whisper API processing
   - Adaptive buffer sizing implemented
   - Performance monitoring in place
   - Emergency fallback modes available

2. Storage Optimization
   - Async I/O for transcription storage
   - Optimized for SATA drives
   - Emergency backup procedures
   - CRC validation ready

3. Thread Safety
   - MonitoringCoordinator handles synchronization
   - Channel-specific locks implemented
   - State management is thread-safe
   - Cleanup coordination in place

4. Windows Integration
   - MMCSS service integration ready
   - Audio service fallbacks implemented
   - Version-specific API paths handled
   - Service monitoring active

### Future Improvements
1. Dynamic history window
2. Async display system
3. Enhanced timestamp precision
4. Memory optimization
5. Whisper API integration
6. Real-time transcription optimization
