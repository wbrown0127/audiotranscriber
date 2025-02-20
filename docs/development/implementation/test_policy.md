# Test Policy

## Overview
This document outlines the testing policies and best practices for the Audio Transcriber project.

## Test Requirements
- Python 3.13.1+
- pytest with threading support
- pytest-asyncio for async test support
- Minimum 2GB available memory
- CPU with multiple cores for concurrency

### Pytest Implementation Notes
All tests use pytest fixtures and assertions for consistent testing patterns:

```python
import pytest
from typing import Generator

@pytest.fixture
def component_setup(monitoring_coordinator: MonitoringCoordinator) -> Generator:
    """Setup component with real system interactions."""
    component = Component(coordinator=monitoring_coordinator)
    yield component
    # Cleanup handled automatically after yield
    component.cleanup()

@pytest.fixture
def thread_manager(monitoring_coordinator: MonitoringCoordinator) -> ThreadManager:
    """Get thread manager interface."""
    return monitoring_coordinator.get_thread_manager()

def test_component_operation(
    component_setup: Component,
    thread_manager: ThreadManager,
    caplog: pytest.LogCaptureFixture
) -> None:
    """Test component operations with proper thread management."""
    # Register thread through interface
    thread_id = thread_manager.register_thread()
    try:
        result = component_setup.process()
        assert result is not None
        assert "Operation completed" in caplog.text
    finally:
        thread_manager.unregister_thread(thread_id)

@pytest.mark.asyncio
async def test_async_operation(
    component_setup: Component,
    thread_manager: ThreadManager
) -> None:
    """Test async operations with proper error handling."""
    thread_id = thread_manager.register_thread()
    try:
        result = await component_setup.async_process()
        assert result.status == "success"
        assert result.metrics["health"] > 90
    finally:
        thread_manager.unregister_thread(thread_id)
```

Key pytest features used:
- Fixtures for setup/cleanup
- Built-in assertions
- Async test support
- Logging capture
- Parametrized testing
- Proper error handling

## Test Structure

### Test Environment

The test environment is built on pytest fixtures that provide real component interactions while maintaining proper dependency management and cleanup. This structure supports the planned coordinator dependency changes and maintains our no-mocking policy.

```python
class TestEnvironment:
    """Test environment configuration."""
    def __init__(self):
        self.managers: Dict[str, Any] = {}
        self.locks: Dict[str, threading.RLock] = {}
        
    def initialize_managers(self) -> None:
        """Initialize managers in dependency order."""
        # Follow coordinator dependency order
        self.managers["state"] = StateManager()
        self.managers["resource"] = ResourceManager()
        self.managers["thread"] = ThreadManager()
        self.managers["monitoring"] = MonitoringManager()
        
    def cleanup_managers(self) -> None:
        """Cleanup in reverse dependency order."""
        for name in reversed(list(self.managers)):
            self.managers[name].cleanup()

class ComponentContext:
    """Component test context with proper lock hierarchy."""
    def __init__(self, env: TestEnvironment):
        self.env = env
        self.locks = self._create_lock_hierarchy()
        
    def _create_lock_hierarchy(self) -> Dict[str, threading.RLock]:
        """Create locks following hierarchy: state -> metrics -> perf -> component -> update"""
        return {
            "state": threading.RLock(),
            "metrics": threading.RLock(),
            "perf": threading.RLock(),
            "component": threading.RLock(),
            "update": threading.RLock()
        }
```

### Core Test Structure

IMPORTANT: NO MOCKING POLICY
All tests must use real components and real system interactions. The only exception is the WhisperTranscriber's OpenAI API calls during development phase.

Each test file must follow this structure:

1. **Environment Setup**
   ```python
   @pytest.fixture
   def test_environment() -> Generator[TestEnvironment, None, None]:
       """Create test environment with real components."""
       env = TestEnvironment()
       try:
           env.initialize_managers()  # Ordered initialization
           yield env
       finally:
           env.cleanup_managers()  # Reverse order cleanup

   @pytest.fixture
   def component_context(
       test_environment: TestEnvironment
   ) -> Generator[ComponentContext, None, None]:
       """Provide component test context."""
       context = ComponentContext(test_environment)
       try:
           context.initialize()
           yield context
       finally:
           context.cleanup()
   ```

2. **Thread Safety**
   - Use ComponentContext for lock hierarchy
   - Handle thread registration through managers
   - Implement proper timeout handling
   - Use ThreadPoolExecutor for concurrent operations
   ```python
   def test_concurrent_operations(
       component_context: ComponentContext,
       caplog: pytest.LogCaptureFixture
   ) -> None:
       with component_context.locks["state"]:
           # Thread-safe operations
           pass
   ```

3. **Resource Management**
   - Access through test environment managers
   - Follow cleanup chains
   - Monitor usage through interfaces
   - Handle allocation/deallocation
   ```python
   def test_resource_usage(
       test_environment: TestEnvironment
   ) -> None:
       resource_manager = test_environment.managers["resource"]
       resource_manager.allocate(...)
   ```

4. **Error Handling**
   - Use pytest.raises for expected errors
   - Preserve error context
   - Implement recovery procedures
   - Validate error states
   ```python
   def test_error_handling(
       component_context: ComponentContext
   ) -> None:
       with pytest.raises(ComponentError) as exc_info:
           # Test error conditions
           pass
       assert "expected error" in str(exc_info.value)
   ```

5. **Metrics and Validation**
   - Use test environment interfaces
   - Verify through managers
   - Track performance
   - Monitor resource usage
   ```python
   def test_metrics(
       test_environment: TestEnvironment
   ) -> None:
       metrics = test_environment.managers["monitoring"].get_metrics()
       assert metrics["health"] > 90
   ```

6. **Logging and Context**
   - Use caplog fixture
   - Include operation context
   - Track test progression
   - Monitor component state
   ```python
   def test_logging(
       component_context: ComponentContext,
       caplog: pytest.LogCaptureFixture
   ) -> None:
       # Test operations
       assert "expected log" in caplog.text
   ```

## Best Practices

### Error Handling
```python
@pytest.fixture
def test_data() -> bytes:
    """Generate test audio data."""
    return np.sin(2 * np.pi * 440 * np.linspace(0, 1, 44100)).astype(np.float32).tobytes()

def test_error_handling(
    component_setup: Component,
    state_manager: StateManager,
    resource_manager: ResourceManager,
    thread_manager: ThreadManager,
    test_data: bytes,
    caplog: pytest.LogCaptureFixture
) -> None:
    """Test error handling with proper context preservation."""
    thread_id = thread_manager.register_thread()
    try:
        # Follow lock hierarchy for operations
        with state_manager.state_lock():
            initial_state = state_manager.get_component_state("component")
            assert initial_state == ComponentState.INITIALIZED
        
        # Attempt operation that should fail
        with (
            state_manager.metrics_lock(),
            state_manager.perf_lock()
        ):
            for channel in ["left", "right"]:
                with component_setup.component_lock():
                    # Trigger error condition with real component
                    component_setup.set_channel_error(channel)
                    with pytest.raises(ComponentError) as exc_info:
                        component_setup.process_channel(channel, test_data)
                    
                    # Verify error context
                    error = exc_info.value
                    assert "channel" in str(error)
                    assert "buffer_health" in str(error)
                    
                    # Verify state transition
                    with state_manager.state_lock():
                        error_state = state_manager.get_component_state("component")
                        assert error_state == ComponentState.ERROR
                    
                    # Verify resource cleanup
                    with component_setup.component_lock():
                        resources = resource_manager.get_allocated_count()
                        assert resources == 0, "Resources not properly cleaned up"
                    
                    # Verify thread health
                    thread_health = thread_manager.get_thread_health(thread_id)
                    assert thread_health["status"] == "error_handled"
                    
                    # Verify error logged with context
                    assert "Component operation failed" in caplog.text
                    assert str(error) in caplog.text
                    assert str(error_state) in caplog.text
                    assert str(thread_health) in caplog.text
                    
    except Exception as e:
        # Log any unexpected errors with full context
        pytest.fail(
            f"Unexpected error: {e}\n"
            f"System health: {component_setup.verify_system_health()}\n"
            f"Lock state: {state_manager.get_lock_state()}"
        )
    finally:
        thread_manager.unregister_thread(thread_id)
```

### Thread Safety
```python
@pytest.fixture
def locks() -> Dict[str, threading.RLock]:
    """Create lock hierarchy for thread safety testing."""
    return {
        "state": threading.RLock(),
        "metrics": threading.RLock(),
        "perf": threading.RLock(),
        "component": threading.RLock(),
        "update": threading.RLock(),
        "error": threading.Lock()
    }

def test_concurrent_operations(
    component_setup: Component,
    state_manager: StateManager,
    thread_manager: ThreadManager,
    test_data: bytes,
    locks: Dict[str, threading.RLock],
    caplog: pytest.LogCaptureFixture
) -> None:
    """Test concurrent operations with proper lock hierarchy and real components."""
    thread_errors: List[Exception] = []
    shutdown_event = threading.Event()
    
    def worker_func() -> None:
        thread_id = None
        try:
            # Register thread through interface
            thread_id = thread_manager.register_thread()
            
            # Follow lock hierarchy for operations
            with locks["state"]:
                current_state = state_manager.get_component_state("component")
                assert current_state == ComponentState.RUNNING, f"Invalid state: {current_state}"
                
            with locks["metrics"], locks["perf"]:
                # Process real audio data with proper channel handling
                for channel in ["left", "right"]:
                    with locks["component"]:
                        result = component_setup.process_channel(channel, test_data)
                        
                    with locks["update"]:
                        component_setup.update_metrics(channel, result)
                        
            # Verify real system health
            assert component_setup.verify_system_health()
            
        except Exception as e:
            with locks["error"]:
                thread_errors.append(e)
                # Log detailed error context
                error_context = {
                    "thread_id": thread_id,
                    "component_state": state_manager.get_component_state("component"),
                    "thread_health": thread_manager.get_thread_health(thread_id)
                }
                pytest.fail(f"Worker failed: {e}\nContext: {error_context}")
        finally:
            if thread_id:
                thread_manager.unregister_thread(thread_id)
    
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(worker_func) for _ in range(4)]
            done, not_done = wait(futures, timeout=30)
            
            if not_done:
                # Force cleanup of timed out operations
                for future in not_done:
                    future.cancel()
                pytest.fail("Operations timed out")
                
            # Check for worker errors
            if thread_errors:
                pytest.fail(f"Workers failed: {thread_errors}")
                
    except Exception as e:
        # Include system state in error context
        pytest.fail(
            f"Concurrent operations failed: {e}\n"
            f"System health: {component_setup.verify_system_health()}\n"
            f"Resource usage: {state_manager.get_resource_usage()}"
        )
```

### Resource Cleanup
```python
@pytest.fixture
def component_cleanup(
    component_setup: Component,
    state_manager: StateManager,
    resource_manager: ResourceManager,
    monitoring_manager: MonitoringManager,
    locks: Dict[str, threading.RLock],
    caplog: pytest.LogCaptureFixture
) -> Generator:
    """Fixture for component cleanup with proper lock hierarchy."""
    yield
    
    try:
        # Follow lock hierarchy: state -> metrics -> perf -> component -> update
        with (
            locks["state"],
            locks["metrics"], 
            locks["perf"],
            locks["component"],
            locks["update"]
        ):
            # Cleanup in reverse dependency order
            for channel in ["left", "right"]:
                component_setup.cleanup_channel(channel)
            component_setup.cleanup()
            
            # Release resources through interfaces
            resource_manager.release_all_resources()
            
            # Stop monitoring through interface
            monitoring_manager.stop_monitoring()
            
            # Cleanup state management
            state_manager.cleanup()
            
    except Exception as e:
        # Log detailed error context
        error_context = {
            "component_state": state_manager.get_component_state("component"),
            "resource_state": resource_manager.get_allocated_count(),
            "thread_state": state_manager.get_thread_health()
        }
        pytest.fail(f"Cleanup failed: {e}\nContext: {error_context}")

@pytest.fixture
def verify_metrics() -> Callable[[Dict[str, Any]], None]:
    """Fixture providing metric validation function."""
    def _verify_metrics(metrics: Dict[str, Any]) -> None:
        """Validate real component metrics with proper error context."""
        try:
            # Basic metric validation
            assert isinstance(metrics, dict)
            assert "timestamp" in metrics
            
            # Resource metrics
            assert "resource_usage" in metrics
            resource_metrics = metrics["resource_usage"]
            assert 0.0 <= resource_metrics["cpu_usage"] < 100.0
            assert resource_metrics["memory_usage"] >= 0
            
            # Performance metrics
            assert "performance_stats" in metrics
            perf_metrics = metrics["performance_stats"]
            assert 0.0 < perf_metrics["latency"] < 1000.0  # Max 1s latency
            
            # Channel-specific metrics
            assert "channel_stats" in metrics
            channel_stats = metrics["channel_stats"]
            for channel in ["left", "right"]:
                assert channel in channel_stats
                assert channel_stats[channel]["buffer_health"] > 90
                assert channel_stats[channel]["overruns"] == 0
                
            # Thread health
            assert "thread_health" in metrics
            assert metrics["thread_health"]["status"] == "healthy"
            
            # Lock state
            assert "lock_state" in metrics
            assert not metrics["lock_state"]["deadlock_detected"]
            
        except AssertionError as e:
            pytest.fail(
                f"Metric validation failed: {e}\n"
                f"Full metrics: {metrics}"
            )
    
    return _verify_metrics

def test_metrics(
    component_setup: Component,
    verify_metrics: Callable[[Dict[str, Any]], None]
) -> None:
    """Test metric validation with real component."""
    metrics = component_setup.get_metrics()
    verify_metrics(metrics)
```

## Test Categories

IMPORTANT: NO MOCKING POLICY
All tests must use real components and real system interactions. The only exception is the WhisperTranscriber's OpenAI API calls during development phase.

### Unit Tests
- Test individual components with real dependencies
- Focus on edge cases with real system behavior
- Fast execution with actual components
- Verify real component interactions

### Integration Tests
- Test real component interactions
- Use actual system resources
- Focus on real-world workflows
- End-to-end scenarios with real hardware

### Performance Tests
- Test under load
- Measure metrics
- Resource monitoring
- Stress testing

## Test Execution

### Current Test Status
```
Core Tests: 46/72 complete (63.9%)
- 46 tests passing
- 26 tests pending:
  * 12 Analysis & Config tests
  * 8 Integration tests
  * 6 Stability tests

Test Categories Breakdown:
1. Analysis & Config (12 pending)
   - Report generation
   - Stability trend analysis
   - Visualization generation
   - System verification
   - Component initialization
   - Device verification

2. Integration Tests (8 pending)
   - Component registration timing
   - Metric update synchronization
   - Error propagation chain

3. Stability Tests (6 pending)
   - Resource management
   - Error recovery
   - Performance metrics
```

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

## Test Infrastructure

### Core Test Script Structure
The run_core_tests.sh script provides the foundation for our test execution framework:

```
tests/
├── results/                           # Test outputs
│   ├── YYYYMMDD_HHMMSS/              # Timestamped test runs
│   │   ├── logs/                     # Detailed test logs
│   │   ├── reports/                  # HTML test reports
│   │   ├── assets/                   # Test resources
│   │   ├── test_info.txt            # Run metadata
│   │   ├── resource_pool_report.html # Pool test results
│   │   ├── core_tests_report.html    # Core test results
│   │   ├── test_output.log          # Filtered output
│   │   └── deadlock_check.log       # Thread analysis
│   ├── test_stability_*/             # Stability results
│   ├── test_transcriber_*/           # Transcriber results
│   └── test_report_*.json            # Result reports
├── run_core_tests.sh                 # Core test executor
├── cleanup_test_outputs.py           # Cleanup automation
├── analyze_results.py                # Analysis tools
└── TEST_POLICY.md                    # Test policy documentation
```

The core test script enforces:
1. Proper environment configuration
   - Project root in PYTHONPATH
   - Consistent pytest options
   - Unbuffered output
   - Windows path compatibility

2. Resource Management
   - Timestamped results
   - Organized test artifacts
   - 5-run retention policy
   - Automatic cleanup

3. Execution Flow
   - ResourcePool validation first
   - Component dependency order
   - Thread safety verification
   - Performance validation
   - State consistency checks

4. Output Processing
   - Noise filtering
   - Error preservation
   - HTML reporting
   - Thread analysis
   - Memory tracking

Note: This structure will inform the implementation of new test files after planned coordinator dependency changes.

### Test Output Management
1. Retention Rules:
   - Stability Tests: Keep last 5 successful runs
   - Transcriber Tests: Keep last 10 runs
   - Test Reports: 30 days retention

2. Size Limits:
   - Stability Tests: 2GB total
   - Transcriber Tests: 1GB total
   - Test Reports: 100MB total

### Analysis Tools
1. cleanup_test_outputs.py:
   - Enforces retention policies
   - Archives important failures
   - Tracks cleanup history
   - Usage:
     ```bash
     python tests/cleanup_test_outputs.py [--force]
     ```

2. analyze_results.py:
   - Generates performance trends
   - Creates visualization plots
   - Produces HTML reports
   - Usage:
     ```bash
     python tests/analyze_results.py [--days 30] [--output report.html]
     ```

## Test Maintenance
- Keep tests up to date with code changes
- Remove obsolete tests
- Update test documentation
- Review test coverage regularly
- Run cleanup_test_outputs.py regularly
- Monitor test output sizes
- Review analysis reports
