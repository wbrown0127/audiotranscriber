#!/usr/bin/env python3
"""
Test runner for Audio Transcriber test suite.
Supports component, integration, and stability tests with consolidated reporting.
"""
import os
import sys
import pytest
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

from utilities.reporting import ReportGenerator

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run Audio Transcriber tests")
    parser.add_argument("--stability", action="store_true",
                      help="Run long-running stability tests (default: False)")
    parser.add_argument("--wasapi", action="store_true",
                      help="Run WASAPI-specific tests (default: False)")
    parser.add_argument("--duration", type=float, default=24.0,
                      help="Duration in hours for stability tests (default: 24.0)")
    parser.add_argument("--pattern", type=str,
                      help="Test file pattern to run (e.g., test_buffer*.py)")
    parser.add_argument("-m", "--marker",
                      help="Only run tests with specific pytest marker (fast/slow/stress)")
    parser.add_argument("-k", "--expression",
                      help="Only run tests matching given expression")
    parser.add_argument("--html", action="store_true",
                      help="Generate HTML report (requires pytest-html)")
    parser.add_argument("--pytest-args", nargs=argparse.REMAINDER,
                      help="Additional arguments to pass to pytest")
    return parser.parse_args()

def setup_test_directories() -> Dict[str, Path]:
    """Setup and return test output directories."""
    base_dir = Path(__file__).parent
    results_dir = base_dir / "results"
    
    # Define simple directory structure
    dirs = {
        "base": results_dir,
        "reports": results_dir / "reports",
        "logs": results_dir / "logs",
        "archives": results_dir / "archives"
    }
    
    # Create directories
    for dir_path in dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)
    
    return dirs

def determine_test_type(args: argparse.Namespace) -> str:
    """Determine the type of tests being run."""
    if args.stability:
        return "stability"
    elif args.wasapi:
        return "integration"
    elif args.marker == "stress":
        return "stability"
    elif args.marker == "slow":
        return "integration"
    return "component"

def build_pytest_args(args: argparse.Namespace, dirs: Dict[str, Path], timestamp: str) -> List[str]:
    """Build pytest command line arguments."""
    pytest_args = []  # Base arguments come from pytest.ini
    
    # Test selection
    if args.stability:
        pytest_args.extend(["-m", "stress"])
    elif args.wasapi:
        pytest_args.extend(["-k", "wasapi"])
    elif args.marker:
        pytest_args.extend(["-m", args.marker])
        
    if args.pattern:
        pytest_args.append(args.pattern)
    else:
        # Default patterns based on mode
        if args.stability:
            pytest_args.append("tests/stability/")
        elif args.wasapi:
            pytest_args.append("tests/integration/test_wasapi*.py")
        else:
            pytest_args.extend(["tests/core/", "tests/integration/"])
            
    if args.expression:
        pytest_args.extend(["-k", args.expression])
        
    # Always generate HTML report
    html_path = dirs["reports"] / f"test_report_{timestamp}.html"
    pytest_args.extend([
        "--html=" + str(html_path),
        "--self-contained-html"
    ])
    
    return pytest_args

def cleanup_old_results(dirs: Dict[str, Path]):
    """Archive old test results."""
    # Let ReportGenerator handle cleanup
    pass

def main() -> int:
    """Run test suite and generate reports."""
    args = parse_args()
    dirs = setup_test_directories()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Configure test environment
    if args.stability:
        os.environ["STABILITY_TEST_DURATION"] = str(args.duration * 3600)
    
    # Initialize test reporter
    reporter = ReportGenerator(str(dirs["base"]))
    
    # Run tests
    pytest_args = build_pytest_args(args, dirs, timestamp)
    if args.pytest_args:
        pytest_args.extend(args.pytest_args)
    
    # Define and register test collection hook
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        if hasattr(item, "metrics"):
            pytest.audio_transcriber_metrics.append(item.metrics)
    
    # Run tests and collect results
    pytest_result = pytest.main(pytest_args)
    
    # Generate and save consolidated report
    if hasattr(pytest, "audio_transcriber_metrics"):
        test_report = reporter.generate_report(pytest.audio_transcriber_metrics)
        report_file = reporter.save_report(test_report)
        
        # Print minimal summary
        summary = test_report["summary"]
        print(f"\nTest Summary:")
        print(f"Total: {summary['total_tests']} | "
              f"Passed: {summary['passed']} | "
              f"Failed: {summary['failed']} | "
              f"Errors: {summary['errors']} | "
              f"Skipped: {summary['skipped']}")
        # Get report paths
        html_path = dirs["reports"] / f"test_report_{timestamp}.html"
        junit_path = dirs["reports"] / f"junit-{timestamp}.xml"
        
        print(f"\nDetailed reports saved to:")
        print(f"- HTML: {html_path}")
        print(f"- JSON: {report_file}")
        print(f"- JUnit XML: {junit_path}")
    
    return pytest_result

if __name__ == "__main__":
    sys.exit(main())
