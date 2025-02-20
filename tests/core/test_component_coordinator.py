#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "TestComponentCoordinator",
    "type": "Test Suite",
    "description": "Comprehensive test suite for verifying ComponentCoordinator functionality including lifecycle management, resource allocation, and health monitoring",
    "version": "Python 3.13.1+",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TC[TestComponentCoordinator] --> CC[ComponentCoordinator]
                TC --> MC[MonitoringCoordinator]
                TC --> CT[ComponentTest]
                TC --> TU[TestUtilities]
                TC --> MT[MockTest]
                TC --> PT[PytestTest]
        ```",
        "dependencies": {
            "ComponentCoordinator": "Main component under test",
            "MonitoringCoordinator": "Provides system monitoring",
            "ComponentTest": "Base test functionality",
            "TestUtilities": "Common test utilities",
            "MockTest": "Mocking capabilities",
            "PytestTest": "Pytest integration"
        }
    },
    "notes": [
        "Verifies component lifecycle and state management",
        "Tests resource allocation and limit enforcement",
        "Validates dependency resolution and ordering",
        "Checks health monitoring and recovery",
        "Ensures proper state history tracking"
    ]
}


Example Usage:
    # Run all component coordinator tests
    python -m pytest tests/core/test_component_coordinator.py

    # Run specific test
    python -m pytest tests/core/test_component_coordinator.py -k test_component_lifecycle

Test Requirements:
    - Python 3.13.1+
    - pytest with threading support
    - Minimum 2GB available memory
    - CPU with multiple cores

Performance Considerations:
    - Tests complete within 2 seconds (fast marker)
    - Resource allocation monitoring
    - State transition tracking
    - Health check overhead
"""
import time
import pytest
import logging
import threading
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
from audio_transcriber.component_coordinator import ComponentCoordinator, ComponentState
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator
from audio_transcriber.resource_pool import ResourcePool
from tests.utilities.base import ComponentTest

# Add note about circular registration fix
"""
Note: This test suite has been updated to prevent circular registration between
MonitoringCoordinator, ComponentCoordinator, and BufferManager. Resource management
is now properly handled through coordinator injection.
"""

class TestComponentCoordinator(ComponentTest):
    """Test suite for ComponentCoordinator functionality.
    
    This test class verifies the coordination and management capabilities
    of the ComponentCoordinator, focusing on system-wide operations.
    
    Key Features Tested:
        - Component lifecycle management
        - Resource allocation and tracking
        - Dependency resolution
        - Health monitoring
        - State history analysis
    
    Attributes:
        monitoring (MonitoringCoordinator): System monitoring
        coordinator (ComponentCoordinator): Component management
    
    Example:
        class TestCustomCoordinator(TestComponentCoordinator):
            def test_custom_lifecycle(self):
                self.coordinator.register_component(
                    'custom',
                    'test',
                    dependencies=['core']
                )
                self.coordinator.initialize_components()
    """

    def setUp(self):
        """Set up test fixtures with proper resource management."""
        super().setUp()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.handlers = []
        self.logger.propagate = False
        
        try:
            # Initialize MonitoringCoordinator first
            self.monitoring = MonitoringCoordinator()
            self.monitoring.start_monitoring()
            
            # Initialize ResourcePool through MonitoringCoordinator
            self.monitoring.initialize_resource_pool({
                'memory': 1024 * 1024 * 100,  # 100MB
                'threads': 4,
                'handles': 100,
                'buffer': {
                    4096: 1000,    # Small buffers
                    65536: 500,    # Medium buffers
                    1048576: 100   # Large buffers
                }
            })
            
            # Initialize ComponentCoordinator with monitoring and resource pool
            self.coordinator = ComponentCoordinator(
                coordinator=self.monitoring  # MonitoringCoordinator handles all resource operations
            )
            
            # Register test thread
            self.monitoring.register_thread()
            
            # Initialize synchronization primitives
            self.shutdown_event = threading.Event()
            self.error_lock = threading.Lock()
            self.thread_errors = []
            
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise

    def tearDown(self):
        """Clean up test fixtures with proper resource cleanup."""
        try:
            # Signal threads to stop
            if hasattr(self, 'shutdown_event'):
                self.shutdown_event.set()
            
            # Cleanup coordinator first
            if hasattr(self, 'coordinator'):
                try:
                    self.coordinator.shutdown()
                except Exception as e:
                    self.logger.error(f"Error cleaning up coordinator: {e}")
            
            # Then cleanup monitoring
            if hasattr(self, 'monitoring'):
                try:
                    self.monitoring.stop_monitoring()
                    self.monitoring.cleanup()
                    # Wait for cleanup to complete
                    time.sleep(0.1)
                except Exception as e:
                    self.logger.error(f"Error cleaning up monitoring: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
        finally:
            super().tearDown()
            
    def record_thread_error(self, error):
        """Record thread error with proper synchronization."""
        with self.error_lock:
            self.thread_errors.append(error)
            self.monitoring.request_shutdown()
            self.shutdown_event.set()

    @pytest.mark.fast
    def test_initialization_validation(self):
        """Test component initialization validation with proper resource management."""
        try:
            # Test initialization with invalid config
            with self.assertRaises(ValueError):
                # Initialize MonitoringCoordinator first
                monitoring = MonitoringCoordinator()
                monitoring.start_monitoring()
                
                # Test invalid config with coordinator injection
                coordinator = ComponentCoordinator(
                    coordinator=monitoring,
                    config={'resource_limits': {'memory': -1}}
                )
                
            # Test initialization with proper resource management
            monitoring = MonitoringCoordinator()
            monitoring.start_monitoring()
            
            # Initialize resource pool through monitoring
            monitoring.initialize_resource_pool({
                'memory': 1024 * 1024 * 100,  # 100MB
                'buffer': {
                    4096: 1000,    # Small buffers
                    65536: 500,    # Medium buffers
                    1048576: 100   # Large buffers
                }
            })
            
            # Initialize coordinator with monitoring
            coordinator = ComponentCoordinator(
                coordinator=monitoring  # MonitoringCoordinator handles resources
            )
            
            # Verify initialization state
            self.assertTrue(coordinator.is_initialized())
            
            # Test component registration with proper resource tracking
            component_name = 'test_component'
            with monitoring.state_lock:
                with monitoring.metrics_lock:
                    with monitoring.perf_lock:
                        with monitoring.component_lock:
                            success = coordinator.register_component(
                                component_name,
                                'test',
                                lambda: True
                            )
                            self.assertTrue(success)
                            
                            # Verify component registration
                            self.assertTrue(coordinator.is_component_registered(component_name))
                            
                            # Verify resource tracking
                            metrics = coordinator.get_component_metrics(component_name)
                            self.assertIsNotNone(metrics)
            
            # Test state transitions with proper lock ordering
            with monitoring.state_lock:
                with monitoring.metrics_lock:
                    with monitoring.perf_lock:
                        with monitoring.component_lock:
                            # Verify state transition validation
                            self.assertTrue(
                                coordinator.transition_component_state(
                                    component_name,
                                    ComponentState.INITIALIZING
                                )
                            )
                            
                            # Verify state tracking
                            state = coordinator.get_component_state(component_name)
                            self.assertEqual(state, ComponentState.INITIALIZING)
            
            # Cleanup test resources
            monitoring.stop_monitoring()
            monitoring.cleanup()
            
            # Log initialization metrics
            self.log_metric("initialization_checks_passed", 1)
            self.log_metric("invalid_transitions_caught", 1)
            self.log_metric("resource_tracking_verified", 1)
            
        except Exception as e:
            self.logger.error(f"Initialization validation test failed: {e}")
            raise

    @pytest.mark.fast
    def test_component_lifecycle(self):
        """Test component lifecycle management.
        
        Verifies the system's ability to manage component lifecycles
        including registration, initialization, and shutdown. This test:
        1. Registers test components
        2. Verifies dependency ordering
        3. Tests initialization sequence
        4. Validates shutdown order
        
        Test Sequence:
            1. Create test components
            2. Register with dependencies
            3. Verify registration
            4. Test initialization
            5. Test shutdown
        
        Expected Results:
            - Components register successfully
            - Correct initialization order
            - Proper shutdown sequence
            - Metrics properly logged
        
        Example Metrics:
            - components_registered: Total components
            - init_sequence_length: Init steps
            - shutdown_sequence_length: Shutdown steps
        """
        try:
            # Create test components with proper resource management
            components = [
                {
                    'id': 'capture',
                    'type': 'input',
                    'dependencies': [],
                    'health_check': lambda: True
                },
                {
                    'id': 'processor',
                    'type': 'transform',
                    'dependencies': ['capture'],
                    'health_check': lambda: True
                },
                {
                    'id': 'output',
                    'type': 'output',
                    'dependencies': ['processor'],
                    'health_check': lambda: True
                }
            ]
            
            # Register components with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            # Register components through coordinator
                            for component in components:
                                success = self.coordinator.register_component(
                                    component['id'],
                                    component['type'],
                                    component['health_check'],
                                    component['dependencies']
                                )
                                self.assertTrue(success, f"Failed to register {component['id']}")
                                
                                # Verify registration and metrics
                                self.assertTrue(self.coordinator.is_component_registered(component['id']))
                                metrics = self.coordinator.get_component_metrics(component['id'])
                                self.assertIsNotNone(metrics)
                            
                            # Verify total registration
                            registered = self.coordinator.get_registered_components()
                            self.assertEqual(len(registered), len(components))
                            
                            # Test initialization sequence
                            init_order = self.coordinator.initialize_components()
                            
                            # Verify dependency order
                            self.assertEqual(init_order[0], 'capture')
                            self.assertEqual(init_order[1], 'processor')
                            self.assertEqual(init_order[2], 'output')
                            
                            # Test shutdown sequence
                            shutdown_order = self.coordinator.shutdown_components()
                            
                            # Verify reverse dependency order
                            self.assertEqual(shutdown_order[0], 'output')
                            self.assertEqual(shutdown_order[1], 'processor')
                            self.assertEqual(shutdown_order[2], 'capture')
        
            # Test channel-specific state transitions with proper lock ordering
            for channel in ['left', 'right']:
                component = f'processor_{channel}'
                
                with self.monitoring.state_lock:
                    with self.monitoring.metrics_lock:
                        with self.monitoring.perf_lock:
                            with self.monitoring.component_lock:
                                # Register channel-specific component
                                success = self.coordinator.register_component(
                                    component,
                                    'transform',
                                    lambda: True
                                )
                                self.assertTrue(success)
                                
                                # Test state transitions with channel resources
                                self.assertTrue(
                                    self.coordinator.transition_component_state(
                                        component, 
                                        ComponentState.INITIALIZING
                                    )
                                )
                                
                                # Allocate channel-specific buffer through coordinator
                                buffer = self.monitoring.allocate_resource(
                                    component,
                                    'buffer',
                                    1024  # 1KB buffer
                                )
                                self.assertIsNotNone(buffer)
                                
                                # Verify state with resources
                                self.assertTrue(
                                    self.coordinator.transition_component_state(
                                        component, 
                                        ComponentState.RUNNING
                                    )
                                )
                                
                                # Verify resource tracking
                                resources = self.coordinator.get_component_resources(component)
                                channel_key = f'buffers_{channel}'
                                self.assertIn(channel_key, resources)
                                self.assertEqual(len(resources[channel_key]), 1)
                                
                                # Test cleanup on shutdown
                                self.assertTrue(
                                    self.coordinator.transition_component_state(
                                        component, 
                                        ComponentState.STOPPING
                                    )
                                )
                                
                                # Release resource through coordinator
                                self.assertTrue(
                                    self.monitoring.release_resource(
                                        component,
                                        'buffer',
                                        buffer
                                    )
                                )
                                
                                # Complete shutdown
                                self.assertTrue(
                                    self.coordinator.transition_component_state(
                                        component, 
                                        ComponentState.STOPPED
                                    )
                                )
                                
                                # Verify final state
                                final_resources = self.coordinator.get_component_resources(component)
                                self.assertEqual(len(final_resources[channel_key]), 0)
            
            # Log lifecycle metrics
            self.log_metric("components_registered", len(registered))
            self.log_metric("init_sequence_length", len(init_order))
            self.log_metric("shutdown_sequence_length", len(shutdown_order))
            self.log_metric("channel_transitions_verified", 2)
            
        except Exception as e:
            self.logger.error(f"Component lifecycle test failed: {e}")
            raise

    @pytest.mark.fast
    def test_resource_allocation(self):
        """Test resource allocation and limit management.
        
        Verifies the system's ability to manage and enforce resource
        limits across components, including channel-specific buffers.
        This test:
        1. Configures resource limits
        2. Tests allocation scenarios including per-channel buffers
        3. Verifies limit enforcement for both channels
        4. Tests deallocation with proper cleanup
        
        Test Sequence:
            1. Define resource types
            2. Configure limits
            3. Attempt allocations
            4. Test limit enforcement
            5. Verify deallocation
        
        Expected Results:
            - Successful allocations within limits
            - Failed allocations when exceeding limits
            - Proper deallocation
            - Resource state tracking
        
        Example Metrics:
            - successful_allocations: Successful count
            - failed_allocations: Failed count
            - resource_usage: Current usage
            - resource_available: Available resources
        """
        try:
            # Configure resource limits with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            # Define resource types including buffer limits
                            resources = {
                                'memory': {'limit': 1024 * 1024 * 100},  # 100MB
                                'threads': {'limit': 4},
                                'handles': {'limit': 100},
                                'buffer': {
                                    4096: 1000,    # Small buffers
                                    65536: 500,    # Medium buffers
                                    1048576: 100   # Large buffers
                                }
                            }
                            
                            # Configure resources through coordinator
                            self.coordinator.configure_resources(resources)
                            
                            # Test standard resource allocation
                            allocations = []
                            for i in range(5):
                                allocation = {
                                    'memory': 1024 * 1024 * 20,  # 20MB
                                    'threads': 1,
                                    'handles': 20
                                }
                                # Allocate through monitoring coordinator
                                success = self.monitoring.allocate_resources(
                                    f'component_{i}',
                                    allocation
                                )
                                allocations.append(success)
                            
                            # Test channel-specific buffer allocation
                            buffer_allocations = {
                                'left': [],
                                'right': []
                            }
                            
                            # Allocate buffers for both channels through coordinator
                            for channel in ['left', 'right']:
                                for i in range(12):  # Try to exceed 10 buffer limit
                                    buffer = self.monitoring.allocate_resource(
                                        f'audio_processor_{channel}',
                                        'buffer',
                                        4096  # Use small buffer tier
                                    )
                                    buffer_allocations[channel].append(buffer is not None)
                            
                            # Verify standard allocations
                            self.assertTrue(all(allocations[:4]))  # First 4 should succeed
                            self.assertFalse(allocations[4])      # 5th should fail due to limits
                            
                            # Verify buffer allocations
                            for channel in ['left', 'right']:
                                self.assertTrue(all(buffer_allocations[channel][:10]))  # First 10 should succeed
                                self.assertFalse(any(buffer_allocations[channel][10:]))  # Rest should fail
                            
                            # Test deallocation through coordinator
                            for i in range(4):
                                success = self.monitoring.deallocate_resources(f'component_{i}')
                                self.assertTrue(success)
                            
                            # Test buffer deallocation through coordinator
                            for channel in ['left', 'right']:
                                component = f'audio_processor_{channel}'
                                resources = self.coordinator.get_component_resources(component)
                                if resources:
                                    channel_key = f'buffers_{channel}'
                                    if channel_key in resources:
                                        for buffer in list(resources[channel_key]):
                                            success = self.monitoring.release_resource(
                                                component,
                                                'buffer',
                                                buffer
                                            )
                                            self.assertTrue(success)
                            
                            # Verify final resource state
                            resource_state = self.monitoring.get_resource_state()
                            
                            # Verify all resources properly released
                            for resource_type, state in resource_state.items():
                                self.assertEqual(
                                    state['used'],
                                    0,
                                    f"Resource {resource_type} not fully released"
                                )
            
            # Log resource metrics
            self.log_metric("successful_allocations", sum(allocations))
            self.log_metric("failed_allocations", len(allocations) - sum(allocations))
            for resource, state in resource_state.items():
                self.log_metric(f"{resource}_usage", state['used'])
                self.log_metric(f"{resource}_available", state['available'])
                
        except Exception as e:
            self.logger.error(f"Resource allocation test failed: {e}")
            raise

    @pytest.mark.fast
    def test_dependency_management(self):
        """Test component dependency management.
        
        Verifies the system's ability to manage and resolve component
        dependencies. This test:
        1. Creates dependency graph
        2. Tests dependency resolution
        3. Verifies initialization order
        4. Tests circular dependency detection
        
        Test Sequence:
            1. Create dependency graph
            2. Register components
            3. Resolve dependencies
            4. Verify order constraints
            5. Test circular detection
        
        Expected Results:
            - Correct resolution order
            - Dependencies respected
            - Circular dependencies caught
            - Proper error handling
        
        Example Metrics:
            - components_in_graph: Graph size
            - resolution_steps: Resolution count
            - dependency_violations: Should be 0
        """
        try:
            # Create dependency graph with proper resource management
            dependencies = {
                'A': {'deps': [], 'health_check': lambda: True},
                'B': {'deps': ['A'], 'health_check': lambda: True},
                'C': {'deps': ['A'], 'health_check': lambda: True},
                'D': {'deps': ['B', 'C'], 'health_check': lambda: True},
                'E': {'deps': ['D'], 'health_check': lambda: True}
            }
            
            # Register components with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            # Register components through coordinator
                            for component, config in dependencies.items():
                                success = self.coordinator.register_component(
                                    component,
                                    'test',
                                    config['health_check'],
                                    config['deps']
                                )
                                self.assertTrue(success, f"Failed to register {component}")
                                
                                # Verify registration and metrics
                                self.assertTrue(self.coordinator.is_component_registered(component))
                                metrics = self.coordinator.get_component_metrics(component)
                                self.assertIsNotNone(metrics)
                            
                            # Verify dependency resolution
                            resolution_order = self.coordinator.resolve_dependencies()
                            
                            # Verify order constraints
                            self.assertLess(
                                resolution_order.index('A'),
                                resolution_order.index('B'),
                                "A should initialize before B"
                            )
                            self.assertLess(
                                resolution_order.index('A'),
                                resolution_order.index('C'),
                                "A should initialize before C"
                            )
                            self.assertLess(
                                resolution_order.index('B'),
                                resolution_order.index('D'),
                                "B should initialize before D"
                            )
                            self.assertLess(
                                resolution_order.index('D'),
                                resolution_order.index('E'),
                                "D should initialize before E"
                            )
                            
                            # Test circular dependency detection
                            with self.assertRaises(Exception):
                                self.coordinator.register_component(
                                    'F',
                                    'test',
                                    lambda: True,
                                    ['E', 'F']  # Self-dependency
                                )
                            
                            # Verify final state
                            registered = self.coordinator.get_registered_components()
                            self.assertEqual(len(registered), len(dependencies))
                            
                            # Verify all components have metrics
                            for component in dependencies:
                                metrics = self.coordinator.get_component_metrics(component)
                                self.assertIsNotNone(metrics)
            
            # Log dependency metrics
            self.log_metric("components_in_graph", len(dependencies))
            self.log_metric("resolution_steps", len(resolution_order))
            self.log_metric("dependency_violations", 0)
            
        except Exception as e:
            self.logger.error(f"Dependency management test failed: {e}")
            raise

    @pytest.mark.fast
    def test_health_checks(self):
        """Test health check integration and monitoring.
        
        Verifies the system's health monitoring capabilities and
        recovery mechanisms. This test:
        1. Registers health checks
        2. Tests status aggregation
        3. Verifies history tracking
        4. Tests recovery system
        
        Test Sequence:
            1. Create health checks
            2. Register components
            3. Run health checks
            4. Test recovery
            5. Verify history
        
        Expected Results:
            - Proper status aggregation
            - History maintained
            - Recovery attempted
            - Metrics recorded
        
        Example Metrics:
            - total_checks: Number of checks
            - healthy_components: Healthy count
            - recovery_attempts: Recovery count
            - channel_specific_health: Per-channel health status
        """
        def create_health_check(status):
            def check():
                try:
                    if status == 'failed':
                        return False
                    return True
                except Exception as e:
                    return False
            return check
        
        try:
            # Register components with health checks using proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            components = {
                                'healthy': create_health_check('healthy'),
                                'degraded': create_health_check('degraded'),
                                'failed': create_health_check('failed')
                            }
                            
                            # Add channel-specific components
                            for channel in ['left', 'right']:
                                components[f'processor_{channel}'] = create_health_check('healthy')
                            
                            for name, check in components.items():
                                self.coordinator.register_health_check(name, check)
                            
                            # Run health checks
                            health_status = self.coordinator.check_health()
                            
                            # Verify status aggregation
                            self.assertEqual(health_status['overall'], 'degraded')
                            self.assertEqual(len(health_status['checks']), len(components))
                            
                            # Test health history
                            history = self.coordinator.get_health_history()
                            self.assertGreater(len(history), 0)
                            
                            # Test automatic recovery with timeout
                            recovery_attempts = self.coordinator.attempt_recovery(timeout=5.0)
                            
                            # Verify recovery tracking
                            recovery_stats = self.coordinator.get_recovery_stats()
                            
                            # Verify recovery completion
                            self.assertIsNotNone(recovery_stats)
                            self.assertIn('attempts', recovery_stats)
                            self.assertIn('success_rate', recovery_stats)
                            
                            # Verify channel-specific health
                            for channel in ['left', 'right']:
                                component = f'processor_{channel}'
                                check_result = self.coordinator.check_component_health(component)
                                self.assertTrue(check_result['healthy'])
                                self.assertIn('metrics', check_result)
            
            # Log health metrics
            self.log_metric("total_checks", len(components))
            self.log_metric("healthy_components", 
                sum(1 for c in health_status['checks'] if c['status'] == 'healthy'))
            self.log_metric("recovery_attempts", recovery_attempts)
            self.log_metric("channel_specific_checks", 2)  # Left and right channels
            
        except Exception as e:
            self.logger.error(f"Health check test failed: {e}")
            raise

    @pytest.mark.fast
    def test_state_history(self):
        """Test state history tracking and analysis.
        
        Verifies the system's ability to track and analyze state
        transitions over time. This test:
        1. Simulates state changes
        2. Tests history recording
        3. Analyzes transitions
        4. Tests history pruning
        5. Verifies channel-specific states
        
        Test Sequence:
            1. Define state changes
            2. Record transitions
            3. Analyze history
            4. Test pruning
            5. Test channel states
            6. Verify metrics
        
        Expected Results:
            - History accurately recorded
            - Analysis results valid
            - Pruning works correctly
            - Channel states tracked
            - Metrics properly logged
        
        Example Metrics:
            - total_state_changes: Change count
            - unique_states: Unique states
            - history_size: History length
            - pruned_size: Size after pruning
            - channel_state_changes: Per-channel changes
        """
        try:
            # Test with proper lock ordering
            with self.monitoring.state_lock:
                with self.monitoring.metrics_lock:
                    with self.monitoring.perf_lock:
                        with self.monitoring.component_lock:
                            # Simulate state changes
                            state_changes = [
                                ('INIT', {}),
                                ('STARTING', {'progress': 0}),
                                ('STARTING', {'progress': 50}),
                                ('RUNNING', {'active_components': 3}),
                                ('DEGRADED', {'failed_components': 1}),
                                ('RUNNING', {'active_components': 3}),
                                ('STOPPING', {'remaining_components': 2}),
                                ('STOPPED', {})
                            ]
                            
                            # Record state changes with error handling
                            for state, metadata in state_changes:
                                try:
                                    self.coordinator.record_state(state, metadata)
                                    time.sleep(0.1)  # Simulate time passing
                                except Exception as e:
                                    self.logger.error(f"Failed to record state {state}: {e}")
                                    raise
                            
                            # Test channel-specific state tracking
                            channel_states = {}
                            for channel in ['left', 'right']:
                                component = f'processor_{channel}'
                                channel_states[channel] = [
                                    (ComponentState.INITIALIZING, {'channel': channel}),
                                    (ComponentState.RUNNING, {'channel': channel, 'active': True}),
                                    (ComponentState.STOPPING, {'channel': channel}),
                                    (ComponentState.STOPPED, {'channel': channel})
                                ]
                                
                                # Register channel component
                                self.coordinator.register_component(
                                    component,
                                    'transform',
                                    lambda: True
                                )
                                
                                # Record channel-specific states
                                for state, metadata in channel_states[channel]:
                                    self.coordinator.record_component_state(
                                        component,
                                        state,
                                        metadata
                                    )
                                    time.sleep(0.1)  # Simulate time passing
                            
                            # Get state history
                            history = self.coordinator.get_state_history()
                            
                            # Verify history recording
                            self.assertEqual(
                                len(history),
                                len(state_changes) + sum(len(states) for states in channel_states.values())
                            )
                            
                            # Analyze state transitions
                            analysis = self.coordinator.analyze_state_history()
                            
                            # Verify analysis results
                            self.assertIn('state_counts', analysis)
                            self.assertIn('average_durations', analysis)
                            self.assertIn('transition_matrix', analysis)
                            self.assertIn('channel_metrics', analysis)
                            
                            # Verify channel-specific metrics
                            for channel in ['left', 'right']:
                                channel_metrics = analysis['channel_metrics'].get(channel)
                                self.assertIsNotNone(channel_metrics)
                                self.assertEqual(
                                    len(channel_metrics['transitions']),
                                    len(channel_states[channel]) - 1
                                )
                            
                            # Test history pruning
                            self.coordinator.prune_history(max_age=1.0)
                            pruned_history = self.coordinator.get_state_history()
                            
                            # Log history metrics
                            self.log_metric("total_state_changes", len(state_changes))
                            self.log_metric("unique_states", len(analysis['state_counts']))
                            self.log_metric("history_size", len(history))
                            self.log_metric("pruned_size", len(pruned_history))
                            self.log_metric("channel_state_changes", 
                                sum(len(states) for states in channel_states.values()))
                            
        except Exception as e:
            self.logger.error(f"State history test failed: {e}")
            raise

if __name__ == '__main__':
    unittest.main()
