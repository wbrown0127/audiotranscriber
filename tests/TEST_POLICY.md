# Test Policy

## Overview
This document outlines the testing policies and best practices for the Audio Transcriber project.

## Test Requirements
- Python 3.13.1+
- pytest with threading support
- pytest-asyncio for async test support
- Minimum 2GB available memory
- CPU with multiple cores for concurrency

### Python 3.13.1 Notes
The following unittest warnings can be safely ignored as they don't affect test execution:
- "coroutine never awaited" warnings from unittest.case
- Deprecation warnings about test case return values
- These warnings are due to unittest's internal checks, while our tests use pytest-asyncio correctly

These warnings only affect tests that:
1. Inherit from ComponentTest AND
2. Use async setUp/tearDown methods OR
3. Have async test methods with @pytest.mark.asyncio

Affected test patterns:
```python
class TestExample(ComponentTest):
    async def asyncSetUp(self):  # Will show warning
        await super().asyncSetUp()
        
    @pytest.mark.asyncio
    async def test_async_operation(self):  # Will show warning
        result = await component.operation()
        self.assertIsNotNone(result)
```

Unaffected test patterns:
```python
class TestExample(ComponentTest):
    def setUp(self):  # No warning
        super().setUp()
        
    def test_sync_operation(self):  # No warning
        result = component.operation()
        self.assertIsNotNone(result)
```

## Test Structure
Each test file should follow this structure:

1. **Setup and Cleanup**
   - Use proper error handling in setUp and tearDown
   - Ensure complete resource cleanup
   - Register and unregister threads properly
   - Clean up mocks to prevent interference

2. **Thread Safety**
   - Use proper synchronization primitives (locks, events)
   - Handle thread registration/unregistration
   - Implement proper timeout handling
   - Use ThreadPoolExecutor for concurrent operations

3. **Resource Management**
   - Configure buffer management properly
   - Implement staged cleanup procedures
   - Monitor resource usage
   - Handle resource allocation/deallocation

4. **Error Handling**
   - Use try/except blocks for all operations
   - Log errors with proper context
   - Implement proper error recovery
   - Validate error states

5. **Metrics and Validation**
   - Validate metric ranges
   - Verify metric consistency
   - Log performance metrics
   - Track resource usage

6. **Logging**
   - Use proper logger configuration
   - Include context in log messages
   - Log performance metrics
   - Track test progression

## Best Practices

### Error Handling
```python
try:
    # Test operations
    result = component.operation()
    self.assertIsNotNone(result)
except Exception as e:
    self.logger.error(f"Operation failed: {e}")
    raise
```

### Thread Safety
```python
def test_concurrent_operations(self):
    self.shutdown_event = threading.Event()
    self.error_lock = threading.Lock()
    self.thread_errors = []
    
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker_func) for _ in range(4)]
            done, not_done = wait(futures, timeout=30)
            if not_done:
                raise TimeoutError("Operations timed out")
    except Exception as e:
        self.logger.error(f"Concurrent operations failed: {e}")
        raise
```

### Resource Cleanup
```python
def tearDown(self):
    try:
        # Cleanup component first
        if hasattr(self, 'component'):
            self.component.cleanup()
        
        # Then cleanup coordinator
        if hasattr(self, 'coordinator'):
            self.coordinator.stop()
            self.coordinator.cleanup()
    except Exception as e:
        self.logger.error(f"Cleanup failed: {e}")
    finally:
        super().tearDown()
```

### Metric Validation
```python
def verify_metrics(self, metrics):
    self.assertGreaterEqual(metrics.cpu_usage, 0.0)
    self.assertLess(metrics.cpu_usage, 100.0)
    self.assertGreaterEqual(metrics.memory_usage, 0)
    self.assertGreater(metrics.latency, 0.0)
```

## Test Categories

### Unit Tests
- Test individual components
- Mock dependencies
- Focus on edge cases
- Fast execution

### Integration Tests
- Test component interactions
- Minimal mocking
- Focus on workflows
- End-to-end scenarios

### Performance Tests
- Test under load
- Measure metrics
- Resource monitoring
- Stress testing

## Test Execution

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run core tests only (recommended for quick validation)
./tests/run_core_tests.sh

# Run specific test
python -m pytest tests/core/test_component.py -k test_name

# Run with coverage
python -m pytest --cov=audio_transcriber tests/
```

Note: Core tests are run using the shell script which automatically handles:
- Test result organization with timestamped directories
- HTML report generation
- Proper error handling and status reporting

### Test Markers
- `@pytest.mark.fast`: Tests that complete within 2 seconds
- `@pytest.mark.slow`: Tests that take longer
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.performance`: Performance tests
- `@pytest.mark.asyncio`: Async tests (required for all async test methods)

## Continuous Integration
- All tests must pass before merge
- Coverage must not decrease
- Performance metrics must meet thresholds
- No resource leaks allowed

## Test Maintenance
- Keep tests up to date with code changes
- Remove obsolete tests
- Update test documentation
- Review test coverage regularly
