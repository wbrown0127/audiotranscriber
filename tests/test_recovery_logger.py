"""
Tests for the recovery logging system.
"""

import pytest
import os
import json
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from audio_transcriber.recovery_logger import (
    RecoveryLogger,
    RecoveryMetrics,
    RecoveryAttempt
)

@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    test_dir = tmp_path / f"test_recovery_{datetime.now():%Y%m%d_%H%M%S}"
    test_dir.mkdir()
    return str(test_dir)

@pytest.fixture
def recovery_logger(temp_dir):
    """Create a RecoveryLogger instance with test directories."""
    return RecoveryLogger(temp_dir)

@pytest.fixture
def sample_metrics():
    """Create sample recovery metrics."""
    now = datetime.now().timestamp()
    return RecoveryMetrics(
        start_time=now,
        end_time=now + 5.0,
        duration=5.0,
        cpu_usage=45.5,
        memory_usage=128.3,
        disk_usage=15.2,
        success=True
    )

@pytest.fixture
def sample_states():
    """Create sample state transition data."""
    return [
        {'state': 'INITIATING', 'timestamp': datetime.now().timestamp()},
        {'state': 'STOPPING_CAPTURE', 'timestamp': datetime.now().timestamp()},
        {'state': 'COMPLETED', 'timestamp': datetime.now().timestamp()}
    ]

@pytest.fixture
def sample_cleanup_status():
    """Create sample cleanup status data."""
    return {
        'phase': 'COMPLETED',
        'completed_steps': ['stop_capture', 'flush_buffers'],
        'failed_steps': [],
        'duration': 2.5
    }

async def test_log_recovery_attempt(recovery_logger, sample_metrics,
                                  sample_states, sample_cleanup_status):
    """Test logging a recovery attempt."""
    await recovery_logger.log_recovery_attempt(
        trigger="test_trigger",
        states=sample_states,
        metrics=sample_metrics,
        cleanup_status=sample_cleanup_status
    )
    
    # Verify attempt was recorded
    assert len(recovery_logger.attempts) == 1
    attempt = recovery_logger.attempts[0]
    assert attempt.trigger == "test_trigger"
    assert attempt.metrics == sample_metrics
    
    # Verify log file was created
    log_files = os.listdir(recovery_logger.recovery_log_dir)
    assert len(log_files) == 1
    
    # Verify log content
    log_path = os.path.join(recovery_logger.recovery_log_dir, log_files[0])
    with open(log_path, 'r') as f:
        log_data = json.load(f)
        assert log_data['trigger'] == "test_trigger"
        assert log_data['states'] == sample_states

async def test_analytics_calculation(recovery_logger, sample_metrics,
                                  sample_states, sample_cleanup_status):
    """Test recovery analytics calculation."""
    # Log multiple attempts with different outcomes
    metrics_success = sample_metrics
    metrics_failure = RecoveryMetrics(
        start_time=datetime.now().timestamp(),
        end_time=datetime.now().timestamp() + 3.0,
        duration=3.0,
        cpu_usage=60.0,
        memory_usage=150.0,
        disk_usage=20.0,
        success=False,
        error="Test failure"
    )
    
    await recovery_logger.log_recovery_attempt(
        "success_trigger", sample_states, metrics_success, sample_cleanup_status
    )
    await recovery_logger.log_recovery_attempt(
        "failure_trigger", sample_states, metrics_failure, sample_cleanup_status
    )
    
    # Get analytics
    analytics = recovery_logger.get_analytics()
    
    # Verify calculations
    assert analytics['total_attempts'] == 2
    assert analytics['success_rate'] == 50.0
    assert 3.0 <= analytics['average_duration'] <= 5.0
    assert analytics['common_triggers'] == {
        'success_trigger': 1,
        'failure_trigger': 1
    }

async def test_state_transition_analysis(recovery_logger, sample_metrics,
                                      sample_cleanup_status):
    """Test analysis of state transition patterns."""
    states = [
        {'state': 'A', 'timestamp': datetime.now().timestamp()},
        {'state': 'B', 'timestamp': datetime.now().timestamp()},
        {'state': 'C', 'timestamp': datetime.now().timestamp()},
        {'state': 'B', 'timestamp': datetime.now().timestamp()},
        {'state': 'C', 'timestamp': datetime.now().timestamp()}
    ]
    
    await recovery_logger.log_recovery_attempt(
        "test_trigger", states, sample_metrics, sample_cleanup_status
    )
    
    analytics = recovery_logger.get_analytics()
    transitions = analytics['state_transitions']
    
    assert transitions['A']['B'] == 1
    assert transitions['B']['C'] == 2

async def test_state_dump_creation(recovery_logger, sample_metrics,
                                sample_states, sample_cleanup_status):
    """Test creation of state dumps for debugging."""
    await recovery_logger.log_recovery_attempt(
        "test_trigger", sample_states, sample_metrics, sample_cleanup_status
    )
    
    attempt_id = recovery_logger.attempts[0].attempt_id
    dump_file = await recovery_logger.create_state_dump(attempt_id)
    
    assert os.path.exists(dump_file)
    with open(dump_file, 'r') as f:
        dump_data = json.load(f)
        assert 'attempt' in dump_data
        assert 'analytics' in dump_data
        assert 'system_state' in dump_data

async def test_cleanup_old_logs(recovery_logger, sample_metrics,
                             sample_states, sample_cleanup_status):
    """Test cleanup of old log files."""
    # Create some log files
    await recovery_logger.log_recovery_attempt(
        "test_trigger", sample_states, sample_metrics, sample_cleanup_status
    )
    
    # Modify file timestamps to simulate old files
    old_time = datetime.now() - timedelta(days=31)
    for directory in [recovery_logger.recovery_log_dir,
                     recovery_logger.analytics_dir,
                     recovery_logger.debug_dir]:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            os.utime(filepath, (old_time.timestamp(), old_time.timestamp()))
    
    # Run cleanup
    await recovery_logger.cleanup_old_logs(days=30)
    
    # Verify old files were removed
    for directory in [recovery_logger.recovery_log_dir,
                     recovery_logger.analytics_dir,
                     recovery_logger.debug_dir]:
        assert len(os.listdir(directory)) == 0

async def test_get_attempt_details(recovery_logger, sample_metrics,
                                sample_states, sample_cleanup_status):
    """Test retrieving details of a specific recovery attempt."""
    await recovery_logger.log_recovery_attempt(
        "test_trigger", sample_states, sample_metrics, sample_cleanup_status
    )
    
    attempt_id = recovery_logger.attempts[0].attempt_id
    details = await recovery_logger.get_attempt_details(attempt_id)
    
    assert details is not None
    assert details['trigger'] == "test_trigger"
    assert details['states'] == sample_states

async def test_error_handling(recovery_logger, sample_metrics,
                           sample_states, sample_cleanup_status):
    """Test error handling in logging operations."""
    # Test with invalid directory
    recovery_logger.recovery_log_dir = "/invalid/path"
    
    await recovery_logger.log_recovery_attempt(
        "test_trigger", sample_states, sample_metrics, sample_cleanup_status
    )
    
    # Verify attempt was still recorded in memory
    assert len(recovery_logger.attempts) == 1
    
    # Test with invalid attempt ID
    details = await recovery_logger.get_attempt_details("invalid_id")
    assert details is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
