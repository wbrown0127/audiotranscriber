"""
Base test classes and utilities for the Audio Transcriber test suite.
"""
import unittest
import logging
import time
import pytest
import asyncio
from typing import Optional, Dict, Any, List
from typing_extensions import Tuple
from datetime import datetime

class BaseTest(unittest.TestCase):
    """Base class for all Audio Transcriber tests."""
    
    async def asyncSetUp(self):
        """Async common setup for all tests."""
        self.start_time = time.time()
        self.test_id = f"{self.__class__.__name__}.{self._testMethodName}"
        self.logger = logging.getLogger(self.test_id)
        self.metrics: Dict[str, Any] = {
            'test_id': self.test_id,
            'status': 'running',
            'start_time': datetime.now().isoformat()
        }
        
        # Ensure pytest has metrics collection initialized
        if not hasattr(pytest, "audio_transcriber_metrics"):
            pytest.audio_transcriber_metrics = []
            
    def setUp(self):
        """Synchronous setup that calls async setup."""
        asyncio.run(self.asyncSetUp())
        
    async def asyncTearDown(self):
        """Async common teardown and metrics collection."""
        duration = time.time() - self.start_time
        
        # Update metrics with final state
        self.metrics.update({
            'duration': duration,
            'end_time': datetime.now().isoformat(),
            'status': self._get_test_status()
        })
        
        # Log completion
        self.logger.info(
            f"Test {self.test_id} completed in {duration:.2f}s "
            f"(Status: {self.metrics['status']})"
        )
        
        # Add metrics to pytest collection
        pytest.audio_transcriber_metrics.append(self.metrics)
        
    def tearDown(self):
        """Synchronous teardown that calls async teardown."""
        asyncio.run(self.asyncTearDown())
        
    def _get_test_status(self) -> str:
        """Get the test status based on test result."""
        if not hasattr(self, '_outcome'):  # For older versions of Python
            return 'unknown'
        
        # Get the test result
        result = self.defaultTestResult()
        
        # Handle different Python/unittest versions
        if hasattr(self, '_feedErrorsToResult'):
            self._feedErrorsToResult(result, self._outcome.errors)
        elif hasattr(self._outcome, 'result'):
            result = self._outcome.result
        
        if not hasattr(result, 'failures'):
            return 'unknown'
            
        if len(result.failures) + len(result.errors) == 0:
            return 'passed'
        elif result.failures:
            return 'failed'
        elif result.errors:
            return 'error'
        elif result.skipped:
            return 'skipped'
        return 'unknown'
        
    def log_metric(self, name: str, value: Any):
        """Record a metric for test reporting."""
        self.metrics[name] = value

class ComponentTest(BaseTest):
    """Base class for fast-running component tests."""
    
    @pytest.mark.fast
    async def asyncSetUp(self):
        """Async setup for component tests."""
        await super().asyncSetUp()
        self.logger = logging.getLogger('component_tests')
        self.metrics['test_type'] = 'component'
        self.metrics['logger_name'] = 'component_tests'
        
    def get_test_config(self):
        """Get standard test configuration."""
        return {
            'channels': 2,
            'sample_width': 2,  # 16-bit
            'sample_rate': 16000,
            'buffer_size': 480  # 30ms at 16kHz
        }

class IntegrationTest(BaseTest):
    """Base class for system integration tests."""
    
    @pytest.mark.slow
    async def asyncSetUp(self):
        """Async setup for integration tests."""
        await super().asyncSetUp()
        self.logger = logging.getLogger('integration_tests')
        self.timeout = 300  # 5 minute timeout
        self.metrics['test_type'] = 'integration'
        self.metrics['logger_name'] = 'integration_tests'

class StabilityTest(BaseTest):
    """Base class for long-running stability tests."""
    
    @pytest.mark.stress
    async def asyncSetUp(self):
        """Async setup for stability tests."""
        await super().asyncSetUp()
        self.logger = logging.getLogger('stability_tests')
        self.duration = 24 * 60 * 60  # 24 hour default
        self.start_timestamp = datetime.now()
        self.metrics['test_type'] = 'stability'
        self.metrics['logger_name'] = 'stability_tests'
        
    def set_duration(self, hours: float):
        """Set the test duration in hours."""
        self.duration = hours * 60 * 60
        
    def should_continue(self) -> bool:
        """Check if stability test should continue running."""
        elapsed = time.time() - self.start_time
        return elapsed < self.duration
        
    def log_stability_metrics(self, uptime: float, 
                            recovery_attempts: int = 0,
                            successful_recoveries: int = 0,
                            buffer_size: Optional[int] = None,
                            active_sessions: Optional[int] = None,
                            issues: Optional[list] = None):
        """Record stability-specific metrics."""
        metrics = {
            'uptime': uptime,
            'recovery_attempts': recovery_attempts,
            'successful_recoveries': successful_recoveries
        }
        if buffer_size is not None:
            metrics['buffer_size'] = buffer_size
        if active_sessions is not None:
            metrics['active_sessions'] = active_sessions
        if issues:
            metrics['issues'] = issues
            
        self.metrics['stability'] = metrics
