"""
Test reporting utilities for generating consolidated test reports.
"""
import json
import logging
import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

class ReportGenerator:
    """Handles collection and generation of test reports."""
    
    def __init__(self, output_dir: Optional[str] = None):
        """Initialize test reporter with organized directory structure."""
        self.base_dir = Path(output_dir) if output_dir else Path(__file__).parent.parent / "results"
        
        # Define directory structure
        self.reports_dir = self.base_dir / "reports"  # For JSON reports
        self.logs_dir = self.base_dir / "logs"        # For log files
        self.archives_dir = self.base_dir / "archives" # For old files
        
        # Ensure base directories exist
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.archives_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger("test_reporting")
        
        # Initialize metrics collection
        if not hasattr(pytest, "audio_transcriber_metrics"):
            pytest.audio_transcriber_metrics = []
        
    def generate_report(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comprehensive test report from collected metrics."""
        report = {
            "summary": self._generate_summary(metrics),
            "components": {
                "core": self._filter_metrics(metrics, "component_tests"),
                "integration": self._filter_metrics(metrics, "integration_tests"),
                "stability": self._filter_metrics(metrics, "stability_tests")
            },
            "timestamp": datetime.now().isoformat(),
            "platform": self._get_platform_info()
        }
        
        # Add WASAPI-specific metrics if available
        wasapi_metrics = self._extract_wasapi_metrics(metrics)
        if wasapi_metrics:
            report["wasapi"] = wasapi_metrics
            
        return report
    
    def save_report(self, report: Dict[str, Any]) -> str:
        """Save test report with proper timestamp and cleanup."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.reports_dir / f"test_report_{timestamp}.json"
        
        # Add timestamp and platform info
        report.update({
            "timestamp": timestamp,
            "platform": self._get_platform_info()
        })
        
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
            
        # Keep only last 10 reports
        self._cleanup_old_files(self.reports_dir, "test_report_*.json", keep=10)
            
        return str(report_file)
    
    def _determine_test_type(self, report: Dict[str, Any]) -> str:
        """Determine primary test type from report metrics."""
        components = report["components"]
        if components["stability"]:
            return "stability"
        elif components["integration"]:
            return "integration"
        return "component"
    
    def _cleanup_old_files(self, directory: Path, pattern: str, keep: int = 10):
        """Archive old files keeping only the specified number of recent files."""
        files = sorted(directory.glob(pattern))
        if len(files) > keep:
            # Move oldest files to archives
            for old_file in files[:-keep]:
                archive_path = self.archives_dir / old_file.name
                if archive_path.exists():
                    archive_path.unlink()  # Remove existing archive if it exists
                old_file.rename(archive_path)
    
    def print_summary(self, report: Dict[str, Any]):
        """Print human-readable test summary."""
        summary = report["summary"]
        
        print("\n=== Test Execution Summary ===")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed']}")
        print(f"Failed: {summary['failed']}")
        print(f"Errors: {summary['errors']}")
        print(f"Skipped: {summary['skipped']}")
        print(f"Total Duration: {summary['total_duration']:.2f}s")
        
        # Component-specific summaries
        for component, tests in report["components"].items():
            if tests:
                print(f"\n=== {component.title()} Tests ===")
                print(f"Count: {len(tests)}")
                failed = len([t for t in tests if t.get("status") != "passed"])
                print(f"Failed: {failed}")
                avg_duration = sum(t.get("duration", 0) for t in tests) / len(tests)
                print(f"Average Duration: {avg_duration:.2f}s")
        
        # WASAPI metrics if available
        if "wasapi" in report:
            print("\n=== WASAPI Stability Metrics ===")
            wasapi = report["wasapi"]
            print(f"Stream Uptime: {wasapi['uptime_percent']:.2f}%")
            print(f"Recovery Success Rate: {wasapi['recovery_success_rate']:.2f}%")
            if "issues" in wasapi and wasapi["issues"]:
                print("\nWASAPI Issues:")
                for issue in wasapi["issues"]:
                    print(f"  - {issue}")
    
    def _generate_summary(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate overall test summary."""
        total_duration = sum(m.get("duration", 0) for m in metrics)
        passed = len([m for m in metrics if m.get("status") == "passed"])
        
        return {
            "total_tests": len(metrics),
            "passed": passed,
            "failed": len([m for m in metrics if m.get("status") == "failed"]),
            "errors": len([m for m in metrics if m.get("status") == "error"]),
            "skipped": len([m for m in metrics if m.get("status") == "skipped"]),
            "total_duration": total_duration
        }
    
    def _filter_metrics(self, metrics: List[Dict[str, Any]], logger_name: str) -> List[Dict[str, Any]]:
        """Filter metrics by logger name."""
        return [m for m in metrics if m.get("logger_name") == logger_name]
    
    def _extract_wasapi_metrics(self, metrics: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Extract and aggregate WASAPI-specific metrics."""
        wasapi_metrics = [m.get("stability", {}) for m in metrics 
                         if "wasapi" in m.get("test_id", "").lower()]
        
        if not wasapi_metrics:
            return None
            
        total_uptime = sum(m.get("uptime", 0) for m in wasapi_metrics)
        total_recovery_attempts = sum(m.get("recovery_attempts", 0) for m in wasapi_metrics)
        successful_recoveries = sum(m.get("successful_recoveries", 0) for m in wasapi_metrics)
        
        issues = set()
        for metric in wasapi_metrics:
            if "issues" in metric:
                issues.update(metric["issues"])
        
        return {
            "uptime_percent": (total_uptime / len(wasapi_metrics)) if wasapi_metrics else 0,
            "recovery_success_rate": (successful_recoveries / total_recovery_attempts * 100) 
                                   if total_recovery_attempts > 0 else 100,
            "issues": sorted(issues)
        }
    
    def _get_platform_info(self) -> Dict[str, str]:
        """Get platform and environment information."""
        import sys
        import platform
        
        return {
            "python_version": sys.version,
            "platform": sys.platform,
            "os": platform.platform(),
            "machine": platform.machine()
        }
