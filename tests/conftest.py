"""
Global test configuration and fixtures.
Configures logging, reporting, and test execution.
"""

import pytest
import logging
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock
import requests
from pytest_html import extras

# Test results directory structure
def get_test_directory():
    """Get test results directory from environment or create default.
    Returns:
        Path: Base directory for test results
    """
    base_dir = Path(os.getenv("RESULTS_DIR", "tests/results/default"))
    
    # Create directory structure if it doesn't exist
    (base_dir / "logs").mkdir(parents=True, exist_ok=True)
    (base_dir / "reports").mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    file_handler = logging.FileHandler(
        base_dir / "logs/pytest.log",
        mode='w'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Configure console handler for minimal output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(
        '%(levelname)s: %(message)s'
    ))
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return base_dir

# Initialize test directory
test_results_dir = get_test_directory()

@pytest.fixture(scope='session')
def results_dir():
    """Provide test results directory."""
    return test_results_dir

def save_test_results(results_dir: Path, test_results: dict):
    """Save test results in multiple formats."""
    reports_dir = results_dir / "reports"
    
    # Save JSON report
    with open(reports_dir / "report.json", 'w') as f:
        json.dump(test_results, f, indent=2)
    
    # Save XML report
    root = ET.Element("testsuites")
    for suite_name, suite_data in test_results.items():
        suite = ET.SubElement(root, "testsuite", name=suite_name)
        for test_name, test_data in suite_data.get('tests', {}).items():
            test = ET.SubElement(suite, "testcase", name=test_name)
            if not test_data.get('passed', True):
                failure = ET.SubElement(test, "failure")
                failure.text = test_data.get('error', 'Test failed')
    
    tree = ET.ElementTree(root)
    tree.write(reports_dir / "junit.xml", encoding='utf-8', xml_declaration=True)
    
    # HTML report is handled by pytest-html plugin

@pytest.fixture(autouse=True)
def mock_api_requests(results_dir):
    """Mock all API requests."""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post:
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "transcription": "Test transcription",
                "confidence": 0.95
            }
        }
        
        mock_get.return_value = mock_response
        mock_post.return_value = mock_response
        
        yield
from typing import Dict, Any
from dataclasses import dataclass, field

@dataclass
class TestState:
    """Global test state tracking."""
    stream_health: bool = True
    recovery_attempts: int = 0
    buffer_size: int = 480
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    last_transcription: str = ""  # Added for transcription tracking
    transcription_confidence: float = 0.0  # Added for confidence tracking
    performance_stats: Dict[str, Any] = field(default_factory=dict)

def pytest_configure(config):
    """Configure pytest with custom markers and reporting."""
    config.addinivalue_line(
        "markers",
        "fast: mark test as a fast test that should complete quickly"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers",
        "stability: mark test as a stability test"
    )
    config.addinivalue_line(
        "markers",
        "wasapi: mark test as requiring WASAPI hardware"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as potentially taking longer than usual"
    )
    config.addinivalue_line(
        "markers",
        "stress: mark test as a stress test that may take significant time"
    )

@pytest.fixture
def test_state():
    """Provide test state fixture."""
    return TestState()

@pytest.fixture(autouse=True)
def test_duration_check(request):
    """Check test duration and warn if too long."""
    yield
    
    # Get test duration from report
    duration = request.node.rep_call.duration if hasattr(request.node, 'rep_call') else 0
    
    # Warn if test takes longer than thresholds
    if (duration > 5.0 and 
        not any(request.node.get_closest_marker(m) 
                for m in ['stability', 'slow', 'stress'])):
        request.node.warn(
            pytest.PytestWarning(
                f"Test {request.node.name} took {duration:.2f}s"
            )
        )

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Process test results for reporting."""
    outcome = yield
    rep = outcome.get_result()
    
    # Store report for duration checking
    setattr(item, f"rep_{rep.when}", rep)
    
    # Only process when test is complete
    if rep.when == "call":
        # Collect test results
        test_results = getattr(item.session, 'test_results', {})
        suite_name = item.parent.name
        if suite_name not in test_results:
            test_results[suite_name] = {'tests': {}}
            
        # Add test result with more details
        test_results[suite_name]['tests'][item.name] = {
            'passed': rep.passed,
            'duration': rep.duration,
            'error': str(call.excinfo) if call.excinfo else None,
            'markers': [m.name for m in item.iter_markers()],
            'timestamp': datetime.now().isoformat()
        }
        
        # Store results
        item.session.test_results = test_results
        
        # Save reports
        save_test_results(test_results_dir, test_results)
        
        # Log minimal info to console
        if not rep.passed:
            logging.error(f"Test failed: {item.name}")
        
        # Log detailed info to file
        logging.info(f"""
Test: {item.name}
Result: {'PASS' if rep.passed else 'FAIL'}
Duration: {rep.duration:.2f}s
Error: {call.excinfo if call.excinfo else 'None'}
""")

@pytest.hookimpl(hookwrapper=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Customize terminal summary output."""
    yield
    
    # Clear terminal reporter's output
    terminalreporter._tw.line()
    
    # Print minimal summary
    passed = len(terminalreporter.stats.get('passed', []))
    failed = len(terminalreporter.stats.get('failed', []))
    skipped = len(terminalreporter.stats.get('skipped', []))
    
    terminalreporter.write_line(
        f"\nResults: {passed} passed, {failed} failed, {skipped} skipped"
    )
    terminalreporter.write_line(
        f"Detailed reports saved in: {test_results_dir}"
    )
