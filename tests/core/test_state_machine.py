"""
COMPONENT_NOTES:
{
    "name": "TestStateMachine",
    "type": "Test Suite",
    "description": "Core test suite for verifying state machine implementation, including state transitions, validation, and recovery sequences",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TSM[TestStateMachine] --> SM[StateMachine]
                TSM --> RS[RecoveryState]
                TSM --> ST[StateTransition]
                SM --> RS
                SM --> ST
                SM --> SV[StateValidator]
                SM --> TH[TransitionHistory]
        ```",
        "dependencies": {
            "StateMachine": "Main component under test",
            "RecoveryState": "State enumeration",
            "StateTransition": "Transition validation",
            "StateValidator": "State invariant checking",
            "TransitionHistory": "State change tracking"
        }
    },
    "notes": [
        "Tests state machine initialization",
        "Verifies valid and invalid state transitions",
        "Tests state invariant checking",
        "Validates transition validation and rollback",
        "Tests complete recovery sequences",
        "Ensures proper error handling"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_state_machine.py",
            "python -m pytest tests/core/test_state_machine.py -k test_recovery_sequence"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "datetime",
            "unittest.mock"
        ],
        "system": {
            "memory": "100MB minimum",
            "storage": "Fast storage for state history"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 1 second",
        "resource_usage": [
            "Minimal memory usage",
            "Light CPU usage",
            "State history storage"
        ]
    }
}
"""

import pytest
from datetime import datetime
from unittest.mock import Mock

from audio_transcriber.state_machine import StateMachine, RecoveryState, StateTransition

@pytest.fixture
def monitoring_coordinator():
    """Create a monitoring coordinator for testing."""
    from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
    coordinator = MonitoringCoordinator()
    coordinator.start_monitoring()
    
    # Initialize resource pool through coordinator
    coordinator.initialize_resource_pool({
        'memory': 1024 * 1024 * 100,  # 100MB
        'threads': 4,
        'handles': 100,
        'buffer': {
            4096: 1000,    # Small buffers
            65536: 500,    # Medium buffers
            1048576: 100   # Large buffers
        }
    })
    
    # Initialize channels
    for channel in ['left', 'right']:
        coordinator.initialize_channel(channel)
        
    yield coordinator
    
    try:
        # Cleanup channels in reverse order
        for channel in ['right', 'left']:
            coordinator.cleanup_channel(channel)
        coordinator.stop_monitoring()
        coordinator.cleanup()
    except Exception as e:
        print(f"Error during coordinator cleanup: {e}")

@pytest.fixture
def state_machine(monitoring_coordinator):
    """Create a state machine instance for testing."""
    # Initialize state machine with coordinator
    machine = StateMachine(coordinator=monitoring_coordinator)
    
    # Initialize channels through coordinator
    for channel in ['left', 'right']:
        machine.initialize_channel(channel)
        
    yield machine
    
    try:
        # Cleanup channels in reverse order
        for channel in ['right', 'left']:
            machine.cleanup_channel(channel)
        machine.cleanup()
    except Exception as e:
        print(f"Error during state machine cleanup: {e}")

def test_initial_state(state_machine):
    """Test state machine initialization."""
    assert state_machine.get_current_state() == RecoveryState.IDLE.value
    assert len(state_machine.get_state_history()) == 0

def test_valid_transition(state_machine):
    """Test valid state transition."""
    # IDLE -> INITIATING is valid
    success = state_machine.transition_to(RecoveryState.INITIATING)
    assert success
    assert state_machine.get_current_state() == RecoveryState.INITIATING.value
    
    # Verify history
    history = state_machine.get_state_history()
    assert len(history) == 1
    assert history[0]['from_state'] == RecoveryState.IDLE.value
    assert history[0]['to_state'] == RecoveryState.INITIATING.value
    assert history[0]['success'] is True

def test_invalid_transition(state_machine):
    """Test invalid state transition."""
    # IDLE -> COMPLETED is invalid
    success = state_machine.transition_to(RecoveryState.COMPLETED)
    assert not success
    assert state_machine.get_current_state() == RecoveryState.IDLE.value
    
    # Verify history
    history = state_machine.get_state_history()
    assert len(history) == 1
    assert history[0]['success'] is False
    assert "Invalid transition" in history[0]['error']

def test_state_invariant(state_machine):
    """Test state invariant checking."""
    # Add invariant that always fails
    state_machine.add_state_invariant(
        RecoveryState.INITIATING,
        lambda: False
    )
    
    # Attempt transition
    success = state_machine.transition_to(RecoveryState.INITIATING)
    assert not success
    assert state_machine.get_current_state() == RecoveryState.IDLE.value
    
    # Verify history
    history = state_machine.get_state_history()
    assert len(history) == 1
    assert history[0]['success'] is False
    assert "State invariants not satisfied" in history[0]['error']

def test_transition_validation(state_machine):
    """Test transition validation."""
    # Add validator that fails
    validator = StateTransition(
        from_state=RecoveryState.IDLE,
        to_state=RecoveryState.INITIATING,
        validation_fn=lambda: False
    )
    state_machine.add_transition_validator(validator)
    
    # Attempt transition
    success = state_machine.transition_to(RecoveryState.INITIATING)
    assert not success
    assert state_machine.get_current_state() == RecoveryState.IDLE.value
    
    # Verify history
    history = state_machine.get_state_history()
    assert len(history) == 1
    assert history[0]['success'] is False
    assert "Transition validation failed" in history[0]['error']

def test_transition_rollback(state_machine):
    """Test transition rollback functionality."""
    rollback_called = False
    
    def mock_rollback():
        nonlocal rollback_called
        rollback_called = True
    
    # Add validator with rollback
    validator = StateTransition(
        from_state=RecoveryState.IDLE,
        to_state=RecoveryState.INITIATING,
        rollback_fn=mock_rollback
    )
    state_machine.add_transition_validator(validator)
    
    # Perform transition then rollback
    state_machine.transition_to(RecoveryState.INITIATING)
    success = state_machine.rollback_transition(
        RecoveryState.IDLE,
        RecoveryState.INITIATING
    )
    
    assert success
    assert rollback_called
    assert state_machine.get_current_state() == RecoveryState.IDLE.value

def test_recovery_sequence(state_machine):
    """Test complete recovery sequence."""
    # Define sequence of states
    sequence = [
        RecoveryState.INITIATING,
        RecoveryState.STOPPING_CAPTURE,
        RecoveryState.FLUSHING_BUFFERS,
        RecoveryState.REINITIALIZING,
        RecoveryState.VERIFYING,
        RecoveryState.COMPLETED
    ]
    
    # Execute sequence
    for state in sequence:
        success = state_machine.transition_to(state)
        assert success
        assert state_machine.get_current_state() == state.value
    
    # Verify history
    history = state_machine.get_state_history()
    assert len(history) == len(sequence)
    for i, event in enumerate(history):
        assert event['success'] is True
        if i > 0:
            assert event['from_state'] == sequence[i-1].value
        assert event['to_state'] == sequence[i].value

def test_failed_recovery_sequence(state_machine):
    """Test recovery sequence with failure."""
    # Start recovery
    state_machine.transition_to(RecoveryState.INITIATING)
    state_machine.transition_to(RecoveryState.STOPPING_CAPTURE)
    
    # Simulate failure
    success = state_machine.transition_to(RecoveryState.FAILED)
    assert success
    assert state_machine.get_current_state() == RecoveryState.FAILED.value
    
    # Can transition back to IDLE from FAILED
    success = state_machine.transition_to(RecoveryState.IDLE)
    assert success
    assert state_machine.get_current_state() == RecoveryState.IDLE.value

def test_state_machine_reset(state_machine):
    """Test state machine reset."""
    # Perform some transitions
    state_machine.transition_to(RecoveryState.INITIATING)
    state_machine.transition_to(RecoveryState.STOPPING_CAPTURE)
    
    # Reset
    state_machine.reset()
    assert state_machine.get_current_state() == RecoveryState.IDLE.value
    
    # Verify reset is recorded in history
    history = state_machine.get_state_history()
    last_event = history[-1]
    assert last_event['to_state'] == RecoveryState.IDLE.value
    assert last_event['error'] == "Reset"

def test_exception_handling(state_machine):
    """Test handling of exceptions during transition."""
    # Add validator that raises exception
    validator = StateTransition(
        from_state=RecoveryState.IDLE,
        to_state=RecoveryState.INITIATING,
        validation_fn=lambda: 1/0  # Will raise ZeroDivisionError
    )
    state_machine.add_transition_validator(validator)
    
    # Attempt transition
    success = state_machine.transition_to(RecoveryState.INITIATING)
    assert not success
    assert state_machine.get_current_state() == RecoveryState.IDLE.value
    
    # Verify error is recorded
    history = state_machine.get_state_history()
    assert len(history) == 1
    assert history[0]['success'] is False
    assert "ZeroDivisionError" in history[0]['error']

def test_channel_specific_states(state_machine):
    """Test channel-specific state management."""
    # Initialize channels
    channels = ['left', 'right']
    for channel in channels:
        state_machine.initialize_channel(channel)
    
    # Test independent channel transitions
    state_machine.transition_to(RecoveryState.INITIATING, channel='left')
    state_machine.transition_to(RecoveryState.STOPPING_CAPTURE, channel='right')
    
    # Verify channel states
    assert state_machine.get_current_state(channel='left') == RecoveryState.INITIATING.value
    assert state_machine.get_current_state(channel='right') == RecoveryState.STOPPING_CAPTURE.value
    
    # Test channel-specific history
    left_history = state_machine.get_state_history(channel='left')
    right_history = state_machine.get_state_history(channel='right')
    
    assert len(left_history) == 1
    assert len(right_history) == 1
    assert left_history[0]['to_state'] == RecoveryState.INITIATING.value
    assert right_history[0]['to_state'] == RecoveryState.STOPPING_CAPTURE.value
    
    # Test channel-specific validation
    validator = StateTransition(
        from_state=RecoveryState.INITIATING,
        to_state=RecoveryState.FLUSHING_BUFFERS,
        validation_fn=lambda channel: channel == 'left'
    )
    state_machine.add_transition_validator(validator)
    
    # Should succeed for left channel
    assert state_machine.transition_to(RecoveryState.FLUSHING_BUFFERS, channel='left')
    # Should fail for right channel
    assert not state_machine.transition_to(RecoveryState.FLUSHING_BUFFERS, channel='right')
    
    # Test channel cleanup
    for channel in channels:
        state_machine.cleanup_channel(channel)
        assert state_machine.get_current_state(channel=channel) == RecoveryState.IDLE.value

def test_performance_metrics(state_machine):
    """Test performance metrics tracking."""
    # Initialize test channels
    channels = ['left', 'right']
    for channel in channels:
        state_machine.initialize_channel(channel)
    
    # Perform transitions and track timing
    start_time = datetime.now()
    
    # System-wide transition
    success = state_machine.transition_to(RecoveryState.INITIATING)
    assert success
    
    # Channel-specific transitions
    for channel in channels:
        success = state_machine.transition_to(RecoveryState.STOPPING_CAPTURE, channel=channel)
        assert success
    
    # Get performance metrics
    metrics = state_machine.get_performance_metrics()
    
    # Verify system-wide metrics
    assert 'transition_count' in metrics
    assert metrics['transition_count'] == 3  # 1 system + 2 channel transitions
    assert 'avg_transition_time' in metrics
    assert metrics['avg_transition_time'] > 0
    assert 'success_rate' in metrics
    assert metrics['success_rate'] == 100.0
    
    # Verify channel-specific metrics
    for channel in channels:
        channel_metrics = state_machine.get_channel_metrics(channel)
        assert 'transition_count' in channel_metrics
        assert channel_metrics['transition_count'] == 1
        assert 'avg_transition_time' in channel_metrics
        assert channel_metrics['avg_transition_time'] > 0
        assert 'success_rate' in channel_metrics
        assert channel_metrics['success_rate'] == 100.0

def test_retry_mechanism(state_machine):
    """Test retry mechanism for failed transitions."""
    # Add failing validator that succeeds on third try
    attempt_count = 0
    def validation_with_retry():
        nonlocal attempt_count
        attempt_count += 1
        return attempt_count >= 3
    
    validator = StateTransition(
        from_state=RecoveryState.IDLE,
        to_state=RecoveryState.INITIATING,
        validation_fn=validation_with_retry
    )
    state_machine.add_transition_validator(validator)
    
    # Configure retry settings
    state_machine.configure_retry({
        'max_attempts': 3,
        'delay_ms': 100
    })
    
    # Attempt transition - should succeed on third try
    success = state_machine.transition_to(RecoveryState.INITIATING)
    assert success
    assert attempt_count == 3
    
    # Verify retry metrics
    metrics = state_machine.get_performance_metrics()
    assert metrics['retry_count'] == 2
    assert metrics['retry_success_rate'] == 100.0
    
    # Test retry exhaustion
    attempt_count = 0  # Reset counter
    success = state_machine.transition_to(RecoveryState.STOPPING_CAPTURE)
    assert not success  # Should fail after 3 attempts
    
    # Verify exhaustion metrics
    metrics = state_machine.get_performance_metrics()
    assert metrics['retry_exhaustion_count'] == 1

def test_staged_cleanup(state_machine):
    """Test staged cleanup coordination."""
    # Initialize channels
    channels = ['left', 'right']
    for channel in channels:
        state_machine.initialize_channel(channel)
    
    # Setup cleanup stages
    cleanup_stages = {
        'pre_cleanup': False,
        'main_cleanup': False,
        'post_cleanup': False
    }
    
    def cleanup_validator(stage):
        def validate():
            cleanup_stages[stage] = True
            return True
        return validate
    
    # Add cleanup validators
    for stage in cleanup_stages:
        validator = StateTransition(
            from_state=RecoveryState.STOPPING_CAPTURE,
            to_state=RecoveryState.IDLE,
            validation_fn=cleanup_validator(stage)
        )
        state_machine.add_cleanup_validator(stage, validator)
    
    # Perform transitions
    state_machine.transition_to(RecoveryState.INITIATING)
    state_machine.transition_to(RecoveryState.STOPPING_CAPTURE)
    
    # Initiate staged cleanup
    success = state_machine.cleanup(staged=True)
    assert success
    
    # Verify all stages executed
    for stage in cleanup_stages:
        assert cleanup_stages[stage], f"Cleanup stage {stage} did not execute"
    
    # Verify final state
    assert state_machine.get_current_state() == RecoveryState.IDLE.value
    
    # Verify cleanup metrics
    metrics = state_machine.get_performance_metrics()
    assert metrics['cleanup_success_rate'] == 100.0
    assert metrics['staged_cleanup_count'] == 1

def test_resource_pool_integration(state_machine, monitoring_coordinator):
    """Test resource pool integration and management."""
    # Initialize test channels
    channels = ['left', 'right']
    for channel in channels:
        state_machine.initialize_channel(channel)
    
    # Get initial resource metrics
    initial_metrics = monitoring_coordinator.get_resource_metrics()
    
    # Test resource allocation during transition
    state_machine.transition_to(RecoveryState.INITIATING)
    
    # Verify allocation through coordinator
    current_metrics = monitoring_coordinator.get_resource_metrics()
    assert current_metrics['allocation_count'] > initial_metrics['allocation_count']
    
    # Test resource cleanup during rollback
    state_machine.rollback_transition(RecoveryState.IDLE, RecoveryState.INITIATING)
    
    # Verify release through coordinator
    current_metrics = monitoring_coordinator.get_resource_metrics()
    assert current_metrics['release_count'] > initial_metrics['release_count']
    
    # Test channel-specific resource management
    for channel in channels:
        initial_channel_metrics = monitoring_coordinator.get_channel_metrics(channel)
        
        state_machine.transition_to(RecoveryState.INITIATING, channel=channel)
        
        # Verify channel-specific allocation
        channel_metrics = monitoring_coordinator.get_channel_metrics(channel)
        assert channel_metrics['allocation_count'] > initial_channel_metrics['allocation_count']
    
    # Test resource cleanup during staged shutdown
    with state_machine.cleanup_stage():
        state_machine.cleanup()
        
        # Verify staged cleanup through coordinator
        final_metrics = monitoring_coordinator.get_resource_metrics()
        assert final_metrics['staged_cleanup_count'] > initial_metrics['staged_cleanup_count']
    
    # Verify final resource metrics
    final_metrics = monitoring_coordinator.get_resource_metrics()
    assert final_metrics['allocation_success_rate'] > 0
    assert final_metrics['release_success_rate'] > 0
    assert final_metrics['current_used'] == 0  # All resources released

def test_component_health_validation(state_machine):
    """Test component health validation during transitions."""
    # Initialize test components
    components = {
        'audio': Mock(health_check=Mock(return_value=True)),
        'buffer': Mock(health_check=Mock(return_value=True)),
        'storage': Mock(health_check=Mock(return_value=True))
    }
    
    # Register components
    for name, component in components.items():
        state_machine.register_component(name, component)
    
    # Test successful health checks
    success = state_machine.transition_to(RecoveryState.INITIATING)
    assert success
    for component in components.values():
        assert component.health_check.called
    
    # Test failed health check
    components['audio'].health_check.return_value = False
    success = state_machine.transition_to(RecoveryState.STOPPING_CAPTURE)
    assert not success
    
    # Verify health check metrics
    metrics = state_machine.get_health_metrics()
    assert metrics['total_checks'] > 0
    assert metrics['failed_checks'] == 1
    assert 'audio' in metrics['component_failures']
    
    # Test component recovery
    components['audio'].health_check.return_value = True
    success = state_machine.transition_to(RecoveryState.STOPPING_CAPTURE)
    assert success
    assert metrics['recovery_count'] == 1

def test_detailed_error_handling(state_machine):
    """Test enhanced error handling with detailed context."""
    # Setup error injection
    def error_validator():
        raise ValueError("Test error with context")
    
    validator = StateTransition(
        from_state=RecoveryState.IDLE,
        to_state=RecoveryState.INITIATING,
        validation_fn=error_validator
    )
    state_machine.add_transition_validator(validator)
    
    # Attempt transition
    try:
        state_machine.transition_to(RecoveryState.INITIATING)
    except Exception as e:
        error_context = state_machine.get_error_context()
        assert error_context['error_type'] == 'ValueError'
        assert error_context['state_context']['from_state'] == RecoveryState.IDLE.value
        assert error_context['state_context']['to_state'] == RecoveryState.INITIATING.value
        assert error_context['component_state'] is not None
        assert error_context['resource_state'] is not None
    
    # Verify error metrics
    metrics = state_machine.get_error_metrics()
    assert metrics['error_count'] > 0
    assert 'ValueError' in metrics['error_types']
    assert metrics['error_types']['ValueError'] == 1

def test_comprehensive_rollback(state_machine):
    """Test comprehensive rollback mechanisms with resource cleanup."""
    # Initialize test channels and resources
    channels = ['left', 'right']
    for channel in channels:
        state_machine.initialize_channel(channel)
    
    # Track rollback steps
    rollback_steps = {
        'resource_cleanup': False,
        'state_restore': False,
        'component_reset': False
    }
    
    def rollback_validator(step):
        def validate():
            rollback_steps[step] = True
            return True
        return validate
    
    # Add rollback validators
    for step in rollback_steps:
        validator = StateTransition(
            from_state=RecoveryState.INITIATING,
            to_state=RecoveryState.IDLE,
            rollback_fn=rollback_validator(step)
        )
        state_machine.add_rollback_validator(validator)
    
    # Perform transition and force rollback
    state_machine.transition_to(RecoveryState.INITIATING)
    state_machine.force_rollback()
    
    # Verify all rollback steps executed
    for step in rollback_steps:
        assert rollback_steps[step], f"Rollback step {step} did not execute"
    
    # Verify rollback metrics
    metrics = state_machine.get_rollback_metrics()
    assert metrics['rollback_count'] > 0
    assert metrics['rollback_success_rate'] == 100.0
    assert metrics['avg_rollback_time'] > 0

def test_concurrent_state_invariants(state_machine):
    """Test multiple state invariants."""
    invariant1_called = False
    invariant2_called = False
    
    def invariant1():
        nonlocal invariant1_called
        invariant1_called = True
        return True
        
    def invariant2():
        nonlocal invariant2_called
        invariant2_called = True
        return True
    
    # Add multiple invariants
    state_machine.add_state_invariant(RecoveryState.INITIATING, invariant1)
    state_machine.add_state_invariant(RecoveryState.INITIATING, invariant2)
    
    # Perform transition
    success = state_machine.transition_to(RecoveryState.INITIATING)
    assert success
    assert invariant1_called and invariant2_called

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
