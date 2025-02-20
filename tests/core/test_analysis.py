"""
COMPONENT_NOTES:
{
    "name": "TestResultAnalysis",
    "type": "Test Suite",
    "description": "Core test suite for verifying test result analysis functionality, including report analysis, visualization generation, and trend detection",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                TRA[TestResultAnalysis] --> RA[ResultAnalyzer]
                TRA --> MC[MonitoringCoordinator]
                TRA --> CT[ComponentTest]
                TRA --> VG[VisualizationGenerator]
                TRA --> RG[ReportGenerator]
                TRA --> FS[FileSystem]
        ```",
        "dependencies": {
            "ResultAnalyzer": "Main component under test",
            "MonitoringCoordinator": "Provides system monitoring",
            "ComponentTest": "Base test functionality",
            "VisualizationGenerator": "Plot generation",
            "ReportGenerator": "HTML report creation",
            "FileSystem": "Test report storage and I/O"
        }
    },
    "notes": [
        "Tests loading and parsing of test reports",
        "Verifies stability trend analysis",
        "Tests transcriber performance analysis",
        "Validates visualization plot generation",
        "Tests HTML report generation",
        "Verifies complete analysis workflow"
    ],
    "usage": {
        "examples": [
            "python -m pytest tests/core/test_analysis.py",
            "python -m pytest tests/core/test_analysis.py -k test_stability_trend_analysis"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "pytest",
            "matplotlib",
            "pandas",
            "json"
        ],
        "system": {
            "memory": "1GB minimum for plot generation",
            "storage": "100MB minimum for test reports"
        }
    },
    "performance": {
        "execution_time": "Tests complete within 5 seconds (fast marker)",
        "resource_usage": [
            "Moderate memory usage during plot generation",
            "Temporary storage for test reports",
            "Cleanup of generated files after tests"
        ]
    }
}
"""
import json
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest
from tests.utilities.base import ComponentTest
from audio_transcriber.analyze_results import ResultAnalyzer
from audio_transcriber.monitoring_coordinator import MonitoringCoordinator

class TestResultAnalysis(ComponentTest):
    """Test result analysis and reporting functionality."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        self.logger = logging.getLogger(self.__class__.__name__)
        
        try:
            # Initialize base class first
            await super().asyncSetUp()
            
            # Create temporary test directory
            self.test_dir = tempfile.mkdtemp()
            self.results_dir = Path(self.test_dir) / 'results'
            self.results_dir.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories needed for plots
            for subdir in ['logs', 'reports', 'archives']:
                (self.results_dir / subdir).mkdir(exist_ok=True)
            
            # Note: Updated to use coordinator for resource management
            self.coordinator = MonitoringCoordinator()
            # Coordinator now handles resource pool initialization
            self.coordinator.start_monitoring()
            
            # Initialize analyzer with coordinator
            self.analyzer = ResultAnalyzer(
                coordinator=self.coordinator,
                days=30,
                results_dir=str(self.results_dir)
            )
            
            # Track initial resource state
            self.initial_resource_metrics = await self.analyzer.get_resource_metrics()
            
            # Create mock test data after analyzer initialization
            await self._create_mock_test_reports()
            
            # Register test thread
            self.coordinator.register_thread()
            
            # Verify test data was created
            if not list(self.results_dir.glob('reports/test_report_*.json')):
                raise RuntimeError("Failed to create mock test reports")
                
        except Exception as e:
            self.logger.error(f"Error during test setup: {e}")
            raise
        
    async def asyncTearDown(self):
        """Clean up test environment."""
        try:
            # Note: Updated cleanup order to match new architecture
            if hasattr(self, 'analyzer'):
                try:
                    # Get final resource state before cleanup
                    final_resource_metrics = await self.analyzer.get_resource_metrics()
                    
                    # Verify no resource leaks
                    self.assertEqual(
                        self.initial_resource_metrics['allocated'],
                        final_resource_metrics['allocated'],
                        "Resource leak detected during test"
                    )
                    
                    await self.analyzer.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up analyzer: {e}")
            
            # Cleanup coordinator last as it manages resources
            if hasattr(self, 'coordinator'):
                try:
                    self.coordinator.stop_monitoring()
                    await self.coordinator.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up coordinator: {e}")
            
            # Finally cleanup test directory
            import shutil
            if hasattr(self, 'test_dir') and Path(self.test_dir).exists():
                shutil.rmtree(self.test_dir)
                
        except Exception as e:
            self.logger.error(f"Error during test cleanup: {e}")
        finally:
            await super().asyncTearDown()
            
    async def _create_mock_test_reports(self):
        """Create mock test report files with proper structure."""
        try:
            reports = []
            for i in range(5):
                report = {
                    'timestamp': (datetime.now(timezone.utc) - timedelta(days=i)).isoformat(),
                    'metrics': {
                        'cpu_usage': 50 + i * 5,
                        'memory_usage': 75 + i * 2,
                        'storage_metrics': {
                            'write_latency': 0.1 + i * 0.05,
                            'buffer_usage': 60 + i * 3,
                            'disk_queue': i,
                            'throughput': 100 - i * 10
                        }
                    },
                    'stability_test': {
                        'success': i > 1,  # First two are failures
                        'duration': 24.0,
                        'metrics': {
                            'cpu_usage': 50 + i * 5,
                            'memory_usage': 75 + i * 2,
                            'success_rate': 0.8 + i * 0.05
                        },
                        'errors': [
                            {'type': f'Error{j}'} for j in range(i % 3)
                        ]
                    },
                    'transcriber_test': {
                        'accuracy': 0.85 + i * 0.02,
                        'processing_time': 1.5 + i * 0.1,
                        'metrics': {
                            'cpu_usage': 60 + i * 3,
                            'memory_usage': 80 + i * 1
                        },
                        'errors': [
                            {'type': f'TranscriberError{j}'} for j in range(i % 2)
                        ]
                    }
                }
                reports.append(report)
                
                # Save in reports directory
                report_file = self.results_dir / 'reports' / f'test_report_{i}.json'
                report_file.parent.mkdir(exist_ok=True)
                with open(report_file, 'w') as f:
                    json.dump(report, f)
                    
            self.mock_reports = reports
            
        except Exception as e:
            self.logger.error(f"Error creating mock test reports: {e}")
            raise
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_report_loading(self):
        """Test loading and parsing of test reports."""
        try:
            reports = await self.analyzer.load_test_reports()
            
            # Verify report loading
            self.assertEqual(len(reports), 5)
            self.assertTrue(all('timestamp' in r for r in reports))
            self.assertTrue(all('stability_test' in r for r in reports))
            self.assertTrue(all('transcriber_test' in r for r in reports))
            
            # Log report metrics
            self.log_metric("total_reports", len(reports))
            self.log_metric("earliest_report_age", 
                           (datetime.now(timezone.utc) - datetime.fromisoformat(reports[0]['timestamp'])).days)
                           
        except Exception as e:
            self.logger.error(f"Report loading test failed: {e}")
            raise
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_stability_trend_analysis(self):
        """Test stability test trend analysis."""
        try:
            reports = await self.analyzer.load_test_reports()
            trends = await self.analyzer.analyze_stability_trends(reports)
            
            # Verify trend analysis results
            self.assertIn('success_rate', trends)
            self.assertIn('avg_cpu_usage', trends)
            self.assertIn('avg_memory_usage', trends)
            self.assertIn('error_counts', trends)
            self.assertIn('test_durations', trends)
            
            # Verify metric calculations
            success_rate = sum(trends['success_rate']) / len(trends['success_rate'])
            self.assertTrue(0 <= success_rate <= 1)
            self.assertTrue(all(0 <= cpu <= 100 for cpu in trends['avg_cpu_usage']))
            self.assertTrue(all(0 <= mem <= 100 for mem in trends['avg_memory_usage']))
            
            # Log trend metrics
            self.log_metric("stability_success_rate", success_rate)
            self.log_metric("avg_cpu_usage", sum(trends['avg_cpu_usage']) / len(trends['avg_cpu_usage']))
            self.log_metric("error_types", len(trends['error_counts']))
            
        except Exception as e:
            self.logger.error(f"Stability trend analysis test failed: {e}")
            raise
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_transcriber_performance_analysis(self):
        """Test transcriber performance analysis."""
        try:
            reports = await self.analyzer.load_test_reports()
            performance = await self.analyzer.analyze_transcriber_performance(reports)
            
            # Verify performance analysis results
            self.assertIn('accuracy_rates', performance)
            self.assertIn('processing_times', performance)
            self.assertIn('error_types', performance)
            self.assertIn('resource_usage', performance)
            
            # Verify metric ranges
            self.assertTrue(all(0 <= acc <= 1 for acc in performance['accuracy_rates']))
            self.assertTrue(all(t > 0 for t in performance['processing_times']))
            
            # Log performance metrics
            self.log_metric("avg_accuracy", 
                           sum(performance['accuracy_rates']) / len(performance['accuracy_rates']))
            self.log_metric("avg_processing_time",
                           sum(performance['processing_times']) / len(performance['processing_times']))
                           
        except Exception as e:
            self.logger.error(f"Transcriber performance analysis test failed: {e}")
            raise
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_visualization_generation(self):
        """Test visualization plot generation."""
        try:
            reports = await self.analyzer.load_test_reports()
            stability_trends = await self.analyzer.analyze_stability_trends(reports)
            transcriber_performance = await self.analyzer.analyze_transcriber_performance(reports)
            
            # Generate plots
            plots = await self.analyzer.generate_plots(stability_trends, transcriber_performance)
            
            # Verify plot generation
            self.assertIn('stability_success', plots)
            self.assertIn('resource_usage', plots)
            self.assertIn('transcriber_accuracy', plots)
            
            # Verify plot files exist
            for plot_file in plots.values():
                self.assertTrue((self.results_dir / plot_file).exists())
                
            # Log plot metrics
            self.log_metric("plots_generated", len(plots))
            self.log_metric("total_plot_size", sum(
                (self.results_dir / plot).stat().st_size for plot in plots.values()
            ))
            
        except Exception as e:
            self.logger.error(f"Visualization generation test failed: {e}")
            raise
        finally:
            # Cleanup plot files
            for plot_file in self.results_dir.glob('*.png'):
                try:
                    plot_file.unlink()
                except Exception as e:
                    self.logger.error(f"Error cleaning up plot file {plot_file}: {e}")
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_html_report_generation(self):
        """Test HTML report generation."""
        try:
            reports = await self.analyzer.load_test_reports()
            stability_trends = await self.analyzer.analyze_stability_trends(reports)
            transcriber_performance = await self.analyzer.analyze_transcriber_performance(reports)
            plots = {
                'stability_success': 'mock_stability.png',
                'resource_usage': 'mock_resource.png',
                'transcriber_accuracy': 'mock_accuracy.png'
            }
            
            # Generate HTML report
            html = await self.analyzer.generate_html_report(
                stability_trends, transcriber_performance, plots
            )
            
            # Verify HTML content
            self.assertIsInstance(html, str)
            self.assertIn('<html>', html)
            self.assertIn('Test Analysis Report', html)
            self.assertTrue(all(plot in html for plot in plots.values()))
            
            # Log report metrics
            self.log_metric("report_size", len(html))
            self.log_metric("plot_references", sum(plot in html for plot in plots.values()))
            
        except Exception as e:
            self.logger.error(f"HTML report generation test failed: {e}")
            raise
        
    @pytest.mark.fast
    @pytest.mark.asyncio
    async def test_full_analysis_workflow(self):
        """Test complete analysis workflow."""
        try:
            output_file = 'test_analysis.html'
            
            # Track resource state before analysis
            initial_metrics = await self.analyzer.get_resource_metrics()
            
            # Run full analysis
            await self.analyzer.run(output_file)
            
            # Track resource state after analysis
            final_metrics = await self.analyzer.get_resource_metrics()
            
            # Verify output files
            self.assertTrue((self.results_dir / output_file).exists())
            self.assertGreater(len(list(self.results_dir.glob('*.png'))), 0)
            
            # Verify report content
            with open(self.results_dir / output_file, 'r') as f:
                content = f.read()
                self.assertIn('Test Analysis Report', content)
                self.assertIn('Stability Test Results', content)
                self.assertIn('Transcriber Performance', content)
            
            # Verify no resource leaks during analysis
            self.assertEqual(
                initial_metrics['allocated'],
                final_metrics['allocated'],
                "Resource leak detected during analysis"
            )
                
            # Log workflow metrics
            self.log_metric("output_files", len(list(self.results_dir.glob('*.*'))))
            self.log_metric("report_file_size", (self.results_dir / output_file).stat().st_size)
            self.log_metric("peak_memory_usage", final_metrics['peak_usage'])
            
        except Exception as e:
            self.logger.error(f"Full analysis workflow test failed: {e}")
            raise
        finally:
            # Cleanup output files
            for output_file in self.results_dir.glob('*.*'):
                try:
                    output_file.unlink()
                except Exception as e:
                    self.logger.error(f"Error cleaning up output file {output_file}: {e}")

if __name__ == '__main__':
    unittest.main()
