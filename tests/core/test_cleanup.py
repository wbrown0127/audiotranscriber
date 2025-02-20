"""
COMPONENT_NOTES:
{
    "name": "TestCleanup",
    "type": "Test Suite",
    "description": "Core test suite for verifying cleanup functionality, including cleanup coordination, output management, and retention policies",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TC[TestCleanup] --> CC[CleanupCoordinator]
                TC --> AT[AudioTranscriber]
                TC --> CU[CleanupUtility]
                TC --> CT[ComponentTest]
                CC --> CS[CleanupStep]
                CC --> CP[CleanupPhase]
                AT --> ST[StorageManager]
                AT --> CM[ComponentManager]
        ```",
        "dependencies": {
            "CleanupCoordinator": "Main component under test",
            "AudioTranscriber": "Provides transcription context",
            "CleanupUtility": "Handles file cleanup operations",
            "ComponentTest": "Base test functionality",
            "CleanupStep": "Step execution management",
            "CleanupPhase": "Phase tracking",
            "StorageManager": "File storage operations",
            "ComponentManager": "Component lifecycle"
        }
    },
    "notes": [
        "Tests cleanup coordinator initialization and step registration",
        "Verifies cleanup step execution order and dependencies",
        "Tests output directory management and classification",
        "Validates retention policy enforcement",
        "Tests size limit enforcement and cleanup",
        "Ensures proper failure detection and handling"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_cleanup.py",
            "python -m pytest tests/core/test_cleanup.py -k test_cleanup_execution_order"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "asyncio",
            "pathlib",
            "tempfile"
        ],
        "system": {
            "storage": "100MB minimum for test files",
            "permissions": "Write access to test directories"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 2 seconds (fast marker)",
        "resource_usage": [
            "Moderate disk I/O for file operations",
            "Minimal memory usage",
            "Proper cleanup of test files"
        ]
    }
}
"""
import os
import json
import shutil
import asyncio
import pytest
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch

from audio_transcriber.cleanup_coordinator import CleanupCoordinator, CleanupStep, CleanupPhase
from audio_transcriber.audio_transcriber import AudioTranscriber
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.component_coordinator import ComponentCoordinator
from tests.utilities.base import ComponentTest
from tests.utilities.cleanup import CleanupUtility

# Add note about sync patterns
"""
Note: This test suite uses synchronous patterns for discrete cleanup operations
as per architecture requirements. Each cleanup operation is atomic and validates
its completion before proceeding to the next step.
"""

class TestCleanupCoordination(ComponentTest):
    """Test cleanup coordination system with proper resource management."""
    
    def setUp(self):
        """Set up test environment with MonitoringCoordinator."""
        super().setUp()
        self.test_dir = os.path.join("tests", "results", f"test_cleanup_{self.test_id}")
        
        # Initialize MonitoringCoordinator first
        self.coordinator = MonitoringCoordinator()
        self.coordinator.start_monitoring()
        
        # Initialize resource pool through coordinator
        self.coordinator.initialize_resource_pool({
            'memory': 1024 * 1024 * 10,  # 10MB for cleanup operations
            'handles': 50,  # File handles for cleanup
            'buffer': {
                4096: 100,    # Small buffers (4KB)
                65536: 50,    # Medium buffers (64KB)
                1048576: 10   # Large buffers (1MB)
            }
        })
        
        # Initialize channels
        for channel in ['left', 'right']:
            self.coordinator.initialize_channel(channel)
        
        # Initialize transcriber with coordinator
        self.transcriber = AudioTranscriber(self.test_dir, coordinator=self.coordinator)
        
        # Register components through coordinator
        self.coordinator.register_component(
            'cleanup_coordinator',
            'service',
            lambda: self.transcriber.cleanup_coordinator.is_valid()
        )
        
        # Get initial resource metrics for verification
        self.initial_metrics = self.coordinator.get_resource_metrics()
        
        # Mock component methods with proper resource management
        self.transcriber.capture.stop_capture = Mock(return_value=True)
        self.transcriber.capture.is_active = Mock(return_value=False)
        self.transcriber.storage.emergency_flush = Mock()
        self.transcriber.storage.get_buffer_size = Mock(return_value=0)
        self.transcriber.storage.cleanup_old_backups = Mock()
        
        # Register test thread
        self.coordinator.register_thread()
        
    def tearDown(self):
        """Clean up test environment with proper resource cleanup."""
        try:
            # Cleanup transcriber first
            if hasattr(self, 'transcriber'):
                self.transcriber.cleanup()
                
            # Then cleanup coordinator
            if hasattr(self, 'coordinator'):
                try:
                    self.coordinator.stop_monitoring()
                    self.coordinator.cleanup()
                    # Wait for cleanup to complete
                    time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"Error cleaning up coordinator: {e}")
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
        finally:
            super().tearDown()
        
    @pytest.mark.fast
    def test_cleanup_initialization(self):
        """Test cleanup coordinator initialization with proper resource management."""
        try:
            # Verify coordinator initialization with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            # Verify cleanup coordinator state
                            assert self.transcriber.cleanup_coordinator is not None
                            assert self.transcriber.cleanup_coordinator.current_phase == CleanupPhase.NOT_STARTED
                            assert len(self.transcriber.cleanup_coordinator.cleanup_steps) == 6
                            
                            # Verify resource registration
                            assert self.coordinator.is_component_registered('cleanup_coordinator')
                            
                            # Verify initial metrics
                            metrics = self.coordinator.get_component_metrics('cleanup_coordinator')
                            assert metrics is not None
                            
            self.log_metric("cleanup_steps", len(self.transcriber.cleanup_coordinator.cleanup_steps))
            self.log_metric("initial_phase", str(self.transcriber.cleanup_coordinator.current_phase))
            
        except Exception as e:
            self.logger.error(f"Cleanup initialization test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_cleanup_step_registration(self):
        """Test cleanup step registration and dependencies with proper validation."""
        try:
            # Verify step registration with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            steps = self.transcriber.cleanup_coordinator.cleanup_steps
                            
                            # Verify step existence and dependencies
                            expected_steps = {
                                "request_shutdown": [],
                                "stop_monitoring": ["request_shutdown"],
                                "stop_capture": ["stop_monitoring"],
                                "flush_storage": ["stop_capture"],
                                "cleanup_backups": ["flush_storage"],
                                "close_logs": ["cleanup_backups"]
                            }
                            
                            for step, deps in expected_steps.items():
                                assert step in steps, f"Missing step: {step}"
                                if deps:
                                    assert all(dep in steps[step].dependencies for dep in deps), \
                                        f"Missing dependencies for {step}: {deps}"
                                
                                # Verify step health
                                assert steps[step].is_valid(), f"Step {step} is not valid"
                                
                                self.log_metric(f"step_{step}_dependencies", len(deps))
                                
            # Verify metrics after registration
            metrics = self.coordinator.get_component_metrics('cleanup_coordinator')
            self.log_metric("registered_steps", len(steps))
            self.log_metric("total_dependencies", sum(len(deps) for deps in expected_steps.values()))
            
        except Exception as e:
            self.logger.error(f"Cleanup step registration test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_cleanup_execution_order(self):
        """Test cleanup steps execute in correct order with proper resource management."""
        try:
            completed_steps = []
            
            def create_mock_cleanup(step_name):
                def mock_cleanup():
                    # Acquire resources through coordinator
                    resource = self.coordinator.allocate_resource('cleanup', 'step', 1024)
                    try:
                        completed_steps.append(step_name)
                    finally:
                        self.coordinator.release_resource('cleanup', 'step', resource)
                return mock_cleanup
            
            # Register cleanup functions with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            for name, step in self.transcriber.cleanup_coordinator.cleanup_steps.items():
                                step.cleanup_fn = create_mock_cleanup(name)
            
            # Execute cleanup
            self.transcriber.cleanup()
            
            expected_order = [
                "request_shutdown",
                "stop_monitoring",
                "stop_capture",
                "flush_storage",
                "cleanup_backups",
                "close_logs"
            ]
            
            # Verify execution order
            assert completed_steps == expected_order, \
                f"Incorrect cleanup order. Expected: {expected_order}, Got: {completed_steps}"
            
            # Verify final state
            assert self.transcriber.cleanup_coordinator.current_phase == CleanupPhase.COMPLETED
            
            # Log metrics
            self.log_metric("steps_completed", len(completed_steps))
            self.log_metric("execution_order_correct", completed_steps == expected_order)
            
        except Exception as e:
            self.logger.error(f"Cleanup execution order test failed: {e}")
            raise

class TestOutputManagement(ComponentTest):
    """Test output cleanup and management with proper resource management."""
    
    def setUp(self):
        """Set up test environment with MonitoringCoordinator."""
        super().setUp()
        
        # Initialize MonitoringCoordinator first
        self.coordinator = MonitoringCoordinator()
        self.coordinator.start_monitoring()
        
        # Create test directory
        self.test_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.test_dir) / 'results'
        self.results_dir.mkdir()
        
        # Initialize cleaner with coordinator
        self.cleaner = CleanupUtility(str(self.test_dir))
        self.cleaner.retention_periods = {
            "results": timedelta(days=1),    # Short retention for tests
            "logs": timedelta(hours=1),
            "stability": timedelta(minutes=30),
            "emergency": timedelta(minutes=5)
        }
        
        # Register cleaner component
        self.coordinator.register_component(
            'output_cleaner',
            'service',
            lambda: self.cleaner.is_valid()
        )
        
        # Create mock test files with proper resource management
        with self.coordinator.state_lock:
            with self.coordinator.metrics_lock:
                with self.coordinator.perf_lock:
                    with self.coordinator.component_lock:
                        self._create_mock_test_files()
        
        # Register test thread
        self.coordinator.register_thread()
        
    def tearDown(self):
        """Clean up test environment with proper resource cleanup."""
        try:
            # Cleanup test files first
            if hasattr(self, 'test_dir'):
                shutil.rmtree(self.test_dir)
                
            # Then cleanup coordinator
            if hasattr(self, 'coordinator'):
                try:
                    self.coordinator.stop_monitoring()
                    self.coordinator.cleanup()
                    # Wait for cleanup to complete
                    time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"Error cleaning up coordinator: {e}")
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
        finally:
            super().tearDown()
            
    def _create_mock_test_files(self):
        """Create mock test files and directories."""
        # Create stability test directories
        for i in range(10):
            test_dir = self.results_dir / f'test_stability_{i}'
            test_dir.mkdir()
            with open(test_dir / 'stability_test.log', 'w') as f:
                f.write('Test completed\n')
                if i < 3:  # Make some tests failed
                    f.write('FAILED: Some error\n')
        
        # Create transcriber test directories
        for i in range(15):
            test_dir = self.results_dir / f'test_transcriber_{i}'
            test_dir.mkdir()
            with open(test_dir / 'stability_test.log', 'w') as f:
                f.write('Test completed\n')
                if i < 4:  # Make some tests failed
                    f.write('ERROR: Some error\n')
        
        # Create test reports
        for i in range(5):
            report_file = self.results_dir / f'test_report_{i}.json'
            with open(report_file, 'w') as f:
                json.dump({'timestamp': datetime.now().isoformat()}, f)
                
    @pytest.mark.fast
    def test_test_directory_management(self):
        """Test test directory detection and classification with proper resource management."""
        try:
            # Verify directory structure with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            stability_dirs = sorted(self.results_dir.glob('test_stability_*'))
                            transcriber_dirs = sorted(self.results_dir.glob('test_transcriber_*'))
                            
                            # Verify directory counts
                            assert len(stability_dirs) == 10, "Expected 10 stability test directories"
                            assert len(transcriber_dirs) == 15, "Expected 15 transcriber test directories"
                            
                            # Verify directory structure
                            for d in stability_dirs:
                                assert d.is_dir(), f"Stability directory {d} not found"
                                assert (d / 'stability_test.log').exists(), f"Log file missing in {d}"
                                
                            for d in transcriber_dirs:
                                assert d.is_dir(), f"Transcriber directory {d} not found"
                                assert (d / 'stability_test.log').exists(), f"Log file missing in {d}"
            
            # Log metrics
            self.log_metric("stability_test_count", len(stability_dirs))
            self.log_metric("transcriber_test_count", len(transcriber_dirs))
            self.log_metric("total_test_dirs", len(stability_dirs) + len(transcriber_dirs))
            
        except Exception as e:
            self.logger.error(f"Directory management test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_failure_detection(self):
        """Test failed test detection with proper resource management."""
        try:
            # Verify test failures with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            stability_dirs = self.cleaner.get_test_dirs('test_stability_*')
                            transcriber_dirs = self.cleaner.get_test_dirs('test_transcriber_*')
                            
                            def is_failed_test(d: Path) -> bool:
                                log_file = d / 'stability_test.log'
                                if not log_file.exists():
                                    return False
                                with open(log_file) as f:
                                    content = f.read()
                                    return 'FAILED:' in content or 'ERROR:' in content
                            
                            # Verify failures with resource tracking
                            resource = self.coordinator.allocate_resource('cleanup', 'failure_check', 1024)
                            try:
                                failed_stability = sum(1 for d in stability_dirs if is_failed_test(d))
                                failed_transcriber = sum(1 for d in transcriber_dirs if is_failed_test(d))
                                
                                # Verify expected failure counts
                                assert failed_stability == 3, f"Expected 3 failed stability tests, got {failed_stability}"
                                assert failed_transcriber == 4, f"Expected 4 failed transcriber tests, got {failed_transcriber}"
                                
                                # Verify failure metrics
                                metrics = self.coordinator.get_component_metrics('output_cleaner')
                                assert metrics is not None
                                assert metrics.get('failed_tests') == failed_stability + failed_transcriber
                            finally:
                                self.coordinator.release_resource('cleanup', 'failure_check', resource)
            
            # Log metrics
            self.log_metric("failed_stability_tests", failed_stability)
            self.log_metric("failed_transcriber_tests", failed_transcriber)
            self.log_metric("total_failed_tests", failed_stability + failed_transcriber)
            
        except Exception as e:
            self.logger.error(f"Failure detection test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_retention_policy(self):
        """Test retention policy enforcement with proper resource management."""
        try:
            # Get initial counts with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            initial_stability = len(list(self.results_dir.glob('test_stability_*')))
                            initial_transcriber = len(list(self.results_dir.glob('test_transcriber_*')))
                            
                            # Execute cleanup with resource tracking
                            resource = self.coordinator.allocate_resource('cleanup', 'retention', 1024)
                            try:
                                # Run cleanups
                                self.cleaner.cleanup_stability_results()  # Keep only 5 most recent
                                self.cleaner.cleanup_old_results()  # Clean up old transcriber tests
                                
                                # Get final counts
                                final_stability = len(list(self.results_dir.glob('test_stability_*')))
                                final_transcriber = len(list(self.results_dir.glob('test_transcriber_*')))
                                
                                # Verify retention counts
                                assert final_stability == 5, f"Expected 5 stability tests after cleanup, got {final_stability}"
                                assert final_transcriber == 10, f"Expected 10 transcriber tests after cleanup, got {final_transcriber}"
                                
                                # Verify cleanup metrics
                                metrics = self.coordinator.get_component_metrics('output_cleaner')
                                assert metrics is not None
                                assert metrics.get('removed_tests') == (initial_stability - final_stability) + (initial_transcriber - final_transcriber)
                            finally:
                                self.coordinator.release_resource('cleanup', 'retention', resource)
            
            # Log metrics
            self.log_metric("initial_stability_tests", initial_stability)
            self.log_metric("final_stability_tests", final_stability)
            self.log_metric("initial_transcriber_tests", initial_transcriber)
            self.log_metric("final_transcriber_tests", final_transcriber)
            self.log_metric("removed_stability_tests", initial_stability - final_stability)
            self.log_metric("removed_transcriber_tests", initial_transcriber - final_transcriber)
            self.log_metric("total_removed_tests", (initial_stability - final_stability) + (initial_transcriber - final_transcriber))
            
        except Exception as e:
            self.logger.error(f"Retention policy test failed: {e}")
            raise
        
    @pytest.mark.fast
    def test_size_limit_enforcement(self):
        """Test size limit enforcement with proper resource management."""
        try:
            # Create large test files with proper lock ordering
            with self.coordinator.state_lock:
                with self.coordinator.metrics_lock:
                    with self.coordinator.perf_lock:
                        with self.coordinator.component_lock:
                            # Create test files with resource tracking
                            resource = self.coordinator.allocate_resource('cleanup', 'size_test', 1024)
                            try:
                                for i in range(3):
                                    test_dir = self.results_dir / f'test_stability_{i}'
                                    with open(test_dir / 'large_file.bin', 'wb') as f:
                                        f.write(b'0' * 1024 * 1024)  # 1MB file
                                
                                # Calculate initial size
                                initial_size = sum(f.stat().st_size for f in self.results_dir.glob('**/*') if f.is_file())
                                
                                # Run cleanup
                                self.cleaner.cleanup_old_results()
                                self.cleaner.cleanup_stability_results()
                                
                                # Calculate final size
                                final_size = sum(f.stat().st_size for f in self.results_dir.glob('**/*') if f.is_file())
                                
                                # Verify size reduction
                                assert final_size < initial_size, \
                                    f"Final size {final_size} not less than initial size {initial_size}"
                                
                                # Verify size metrics
                                metrics = self.coordinator.get_component_metrics('output_cleaner')
                                assert metrics is not None
                                assert metrics.get('size_reduced') == initial_size - final_size
                            finally:
                                self.coordinator.release_resource('cleanup', 'size_test', resource)
            
            # Log metrics
            self.log_metric("initial_total_size", initial_size)
            self.log_metric("final_total_size", final_size)
            self.log_metric("size_reduced", initial_size - final_size)
            self.log_metric("size_reduced_mb", (initial_size - final_size) / (1024 * 1024))
            
        except Exception as e:
            self.logger.error(f"Size limit enforcement test failed: {e}")
            raise
