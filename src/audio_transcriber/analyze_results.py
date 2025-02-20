#!/usr/bin/env python3
"""
COMPONENT_NOTES:
{
    "name": "ResultAnalyzer",
    "type": "Analysis Component",
    "description": "Test result analysis system that generates comprehensive reports and visualizations from test results, including performance metrics and statistical analysis",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                RA[ResultAnalyzer] --> MP[MetricPlotter]
                RA --> SA[StatisticalAnalyzer]
                RA --> RG[ReportGenerator]
                MP --> PL[Plots]
                SA --> ST[Statistics]
                RG --> HR[HTMLReport]
                RA --> MN[MetricNames]
                MP --> NP[NumPy]
                MP --> PLT[Matplotlib]
                SA --> SP[SciPy]
        ```",
        "dependencies": {
            "MetricPlotter": "Visualization generation",
            "StatisticalAnalyzer": "Statistical calculations",
            "ReportGenerator": "HTML report creation",
            "MetricNames": "Standardized metric naming",
            "NumPy": "Numerical computations",
            "Matplotlib": "Plot generation",
            "SciPy": "Statistical functions"
        }
    },
    "notes": [
        "Analyzes test results over configurable time periods",
        "Generates statistical analysis with confidence intervals",
        "Creates visualizations of performance trends",
        "Produces comprehensive HTML reports",
        "Tracks system stability and performance",
        "Provides actionable recommendations"
    ],
    "usage": {
        "examples": [
            "analyzer = ResultAnalyzer(days=30)",
            "analyzer.run('test_analysis.html')",
            "python analyze_results.py --days 30 --output report.html"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "numpy",
            "matplotlib",
            "scipy",
            "typing_extensions"
        ],
        "system": {
            "storage": "Space for report artifacts",
            "memory": "Sufficient for data analysis"
        }
    },
    "performance": {
        "execution_time": "Scales with analysis period",
        "resource_usage": [
            "Memory usage scales with dataset size",
            "CPU intensive for statistical calculations",
            "Disk I/O for report generation",
            "GPU acceleration for plotting (if available)"
        ]
    }
}
"""

import json
import argparse
import logging
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from enum import Enum
from html import escape
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
from typing import Dict, List, Any, Optional
from typing_extensions import Tuple

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)5s] %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent.parent / 'tests/results/analysis.log'),
        logging.StreamHandler()
    ]
)

class MetricNames(Enum):
    """Standardized metric names."""
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    SUCCESS_RATE = "success_rate"
    WRITE_LATENCY = "write_latency"
    BUFFER_USAGE = "buffer_usage"
    DISK_QUEUE = "disk_queue_length"
    THROUGHPUT = "write_throughput"
    ACCURACY = "accuracy"
    PROCESSING_TIME = "processing_time"

def parse_args():
    parser = argparse.ArgumentParser(description='Analyze test results and generate reports')
    parser.add_argument('--days', type=int, default=30, help='Number of days of history to analyze')
    parser.add_argument('--output', type=str, default='test_analysis.html', help='Output report file')
    parser.add_argument('--results-dir', type=str, help='Test results directory (optional)')
    return parser.parse_args()

class ResultAnalyzer:
    def __init__(self, coordinator=None, days: int = 30, results_dir: Optional[str] = None):
        """Initialize analyzer with optional coordinator and configuration.
        
        Args:
            coordinator: Optional MonitoringCoordinator instance
            days: Number of days of history to analyze
            results_dir: Optional custom results directory path
        """
        # Allow custom results directory or use default
        self.results_dir = (Path(results_dir) if results_dir 
                           else Path(__file__).parent.parent.parent / 'tests/results')
        if not self.results_dir.exists():
            raise ValueError(f"Results directory not found: {self.results_dir}")
            
        self.coordinator = coordinator
        self.days = days
        self.cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        self.version = "1.0.0"  # Report version tracking
        logger.info(f"Initializing analysis for past {days} days")
        
        # Initialize coordinator state
        if self.coordinator:
            self.coordinator.update_state(
                analyzer_initialized=True,
                analysis_window_days=days
            )
        
    def get_metric(self, data: Dict, metric: MetricNames, default: Any = 0) -> Any:
        """Safely get metric value with standardized names."""
        try:
            if isinstance(data, dict):
                return data.get('metrics', {}).get(metric.value, default)
            return default
        except Exception as e:
            logger.error(f"Error getting metric {metric.value}: {e}")
            return default
            
    def calculate_rate(self, values: List[float]) -> float:
        """Safely calculate rate with error handling."""
        if not values:
            return 0.0
        try:
            return sum(values) / len(values)
        except ZeroDivisionError:
            logger.error("No values available for rate calculation")
            return 0.0
        except Exception as e:
            logger.error(f"Error calculating rate: {e}")
            return 0.0
            
    def validate_data(self, data: Dict) -> bool:
        """Validate report data structure."""
        required_fields = {'timestamp', 'metrics', 'errors'}
        return all(field in data for field in required_fields)

    def load_test_reports(self) -> List[Dict]:
        """Load all test reports within the analysis window."""
        logger.info("Loading test reports...")
        reports = []
        try:
            # Track report loading progress
            total_files = len(list(self.results_dir.glob('**/test_report_*.json')))
            processed_files = 0
            
            # Search recursively in reports directory
            for report_file in self.results_dir.glob('**/test_report_*.json'):
                if report_file.stat().st_mtime >= self.cutoff_date.timestamp():
                    try:
                        with open(report_file, 'r') as f:
                            data = json.load(f)
                            if self.validate_data(data):
                                reports.append(data)
                                if self.coordinator:
                                    self.coordinator.update_state(
                                        report_loaded=True,
                                        report_file=str(report_file)
                                    )
                            else:
                                logger.warning(f"Invalid report structure in {report_file}")
                                if self.coordinator:
                                    self.coordinator.handle_error(
                                        ValueError(f"Invalid report structure"),
                                        "analyzer"
                                    )
                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing {report_file}: {e}")
                        if self.coordinator:
                            self.coordinator.handle_error(e, "analyzer")
                    except Exception as e:
                        logger.error(f"Error loading {report_file}: {e}")
                        if self.coordinator:
                            self.coordinator.handle_error(e, "analyzer")
                            
                processed_files += 1
                if self.coordinator:
                    self.coordinator.update_state(
                        loading_progress=processed_files / total_files * 100
                    )
                        
            if not reports:
                logger.warning("No valid test reports found in analysis window")
                if self.coordinator:
                    self.coordinator.update_state(reports_found=False)
                    
            reports = sorted(reports, key=lambda x: x.get('timestamp', ''))
            
            if self.coordinator:
                self.coordinator.update_state(
                    reports_loaded=len(reports),
                    loading_complete=True
                )
                
            return reports
            
        except Exception as e:
            logger.error(f"Error scanning results directory: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "analyzer")
            return []
    
    def calculate_statistics(self, data: List[float], confidence: float = 0.95) -> Dict[str, float]:
        """Calculate statistical measures for a dataset."""
        if not data:
            return {
                'mean': 0.0,
                'std': 0.0,
                'ci': 0.0,
                'min': 0.0,
                'max': 0.0
            }
            
        try:
            data_array = np.array(data)
            mean = np.mean(data_array)
            std = np.std(data_array)
            
            # Calculate confidence interval
            if len(data) > 1:
                ci = std * stats.t.ppf((1 + confidence) / 2, len(data)-1)
            else:
                ci = 0.0
                
            return {
                'mean': mean,
                'std': std,
                'ci': ci,
                'min': np.min(data_array),
                'max': np.max(data_array)
            }
        except Exception as e:
            logger.error(f"Error calculating statistics: {e}")
            return {
                'mean': 0.0,
                'std': 0.0,
                'ci': 0.0,
                'min': 0.0,
                'max': 0.0
            }

    def analyze_stability_trends(self, reports: List[Dict]) -> Dict:
        """Analyze stability test trends including storage performance."""
        trends = {
            'success_rate': [],
            'avg_cpu_usage': [],
            'avg_memory_usage': [],
            'error_counts': defaultdict(int),
            'test_durations': [],
            'storage_metrics': {
                'write_latency': [],
                'buffer_usage': [],
                'disk_queue': [],
                'throughput': []
            }
        }
        
        try:
            for report in reports:
                if 'stability_test' in report:
                    test = report['stability_test']
                    # Use standardized metric names
                    trends['success_rate'].append(
                        self.get_metric(test, MetricNames.SUCCESS_RATE, False)
                    )
                    trends['avg_cpu_usage'].append(
                        self.get_metric(test, MetricNames.CPU_USAGE, 0)
                    )
                    trends['avg_memory_usage'].append(
                        self.get_metric(test, MetricNames.MEMORY_USAGE, 0)
                    )
                    trends['test_durations'].append(
                        test.get('duration', 0)
                    )
                    
                    # Track storage performance metrics
                    if 'storage_metrics' in test.get('metrics', {}):
                        storage = test['metrics']['storage_metrics']
                        trends['storage_metrics']['write_latency'].append(
                            self.get_metric(storage, MetricNames.WRITE_LATENCY, 0)
                        )
                        trends['storage_metrics']['buffer_usage'].append(
                            self.get_metric(storage, MetricNames.BUFFER_USAGE, 0)
                        )
                        trends['storage_metrics']['disk_queue'].append(
                            self.get_metric(storage, MetricNames.DISK_QUEUE, 0)
                        )
                        trends['storage_metrics']['throughput'].append(
                            self.get_metric(storage, MetricNames.THROUGHPUT, 0)
                        )
                    
                    for error in test.get('errors', []):
                        trends['error_counts'][error['type']] += 1
                        
            # Calculate statistics for each metric
            trends['statistics'] = {
                'cpu_usage': self.calculate_statistics(trends['avg_cpu_usage']),
                'memory_usage': self.calculate_statistics(trends['avg_memory_usage']),
                'success_rate': self.calculate_statistics(trends['success_rate']),
                'write_latency': self.calculate_statistics(trends['storage_metrics']['write_latency']),
                'buffer_usage': self.calculate_statistics(trends['storage_metrics']['buffer_usage'])
            }
            
            return trends
            
        except Exception as e:
            logger.error(f"Error analyzing stability trends: {e}")
            return trends
    
    def analyze_transcriber_performance(self, reports: List[Dict]) -> Dict:
        """Analyze transcriber test performance."""
        performance = {
            'accuracy_rates': [],
            'processing_times': [],
            'error_types': defaultdict(int),
            'resource_usage': []
        }
        
        for report in reports:
            if 'transcriber_test' in report:
                test = report['transcriber_test']
                performance['accuracy_rates'].append(
                    test.get('accuracy', 0)
                )
                performance['processing_times'].append(
                    test.get('processing_time', 0)
                )
                performance['resource_usage'].append({
                    'cpu': test.get('metrics', {}).get('cpu_usage', 0),
                    'memory': test.get('metrics', {}).get('memory_usage', 0)
                })
                for error in test.get('errors', []):
                    performance['error_types'][error['type']] += 1
        
        return performance
    
    def plot_with_confidence(self, data: List[float], label: str, color: str = 'blue',
                           confidence: float = 0.95) -> None:
        """Plot data with confidence intervals."""
        try:
            if not data:
                return
                
            x = range(len(data))
            y = np.array(data)
            
            stats = self.calculate_statistics(data, confidence)
            
            plt.plot(x, y, label=f'{label}\nMean: {stats["mean"]:.2f} ± {stats["ci"]:.2f}',
                    color=color)
            
            # Add confidence interval shading
            plt.fill_between(x,
                           y - stats['ci'],
                           y + stats['ci'],
                           color=color, alpha=0.2)
                           
            # Add trend line
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)
            plt.plot(x, p(x), "--", color=color, alpha=0.8,
                    label=f'Trend: {z[0]:.2e}x + {z[1]:.2f}')
                    
        except Exception as e:
            logger.error(f"Error plotting with confidence: {e}")

    def generate_plots(self, stability_trends: Dict, transcriber_performance: Dict) -> Dict:
        """Generate visualization plots including storage performance."""
        plots = {}
        try:
            plt.style.use('seaborn')  # Use better styling
            
            # Stability Test Success Rate with Error Bars
            plt.figure(figsize=(10, 6))
            stats = stability_trends['statistics']['success_rate']
            plt.bar(['Success Rate'], [stats['mean'] * 100],
                   yerr=[stats['ci'] * 100],
                   capsize=5)
            plt.title('Stability Test Success Rate')
            plt.ylabel('Percentage')
            plots['stability_success'] = 'stability_success.png'
            plt.savefig(self.results_dir / plots['stability_success'], dpi=300, bbox_inches='tight')
            plt.close()
            
            # Resource Usage Trends with Confidence Intervals
            plt.figure(figsize=(12, 6))
            self.plot_with_confidence(stability_trends['avg_cpu_usage'],
                                    'CPU Usage', 'blue')
            self.plot_with_confidence(stability_trends['avg_memory_usage'],
                                    'Memory Usage', 'red')
            plt.title('Resource Usage Trends')
            plt.xlabel('Test Run')
            plt.ylabel('Usage %')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plots['resource_usage'] = 'resource_usage.png'
            plt.savefig(self.results_dir / plots['resource_usage'], dpi=300, bbox_inches='tight')
            plt.close()
            
            # Transcriber Accuracy with Confidence Intervals
            plt.figure(figsize=(10, 6))
            self.plot_with_confidence(transcriber_performance['accuracy_rates'],
                                    'Accuracy', 'green')
            plt.title('Transcription Accuracy Trend')
            plt.xlabel('Test Run')
            plt.ylabel('Accuracy %')
            plt.grid(True, alpha=0.3)
            plots['transcriber_accuracy'] = 'transcriber_accuracy.png'
            plt.savefig(self.results_dir / plots['transcriber_accuracy'], dpi=300, bbox_inches='tight')
            plt.close()
            
            # Storage Performance Plot with Statistical Analysis
            if stability_trends['storage_metrics']['write_latency']:
                plt.figure(figsize=(12, 8))
                
                # Write Latency with Confidence Intervals
                plt.subplot(2, 1, 1)
                self.plot_with_confidence(
                    stability_trends['storage_metrics']['write_latency'],
                    'Write Latency (s)', 'blue'
                )
                plt.axhline(y=0.5, color='r', linestyle='--',
                           label='Phase 3 Target (0.5s)')
                plt.title('Storage Performance Metrics')
                plt.ylabel('Seconds')
                plt.legend()
                plt.grid(True, alpha=0.3)
                
                # Buffer Usage with Confidence Intervals
                plt.subplot(2, 1, 2)
                self.plot_with_confidence(
                    stability_trends['storage_metrics']['buffer_usage'],
                    'Buffer Usage %', 'green'
                )
                plt.axhline(y=80, color='r', linestyle='--',
                           label='Buffer Threshold (80%)')
                plt.ylabel('Percentage')
                plt.xlabel('Test Run')
                plt.legend()
                plt.grid(True, alpha=0.3)
                
                plt.tight_layout()
                plots['storage_performance'] = 'storage_performance.png'
                plt.savefig(self.results_dir / plots['storage_performance'], dpi=300, bbox_inches='tight')
                plt.close()
                
            return plots
            
        except Exception as e:
            logger.error(f"Error generating plots: {e}")
            return plots
        
        return plots
    
    def format_table_row(self, key: str, value: Any) -> str:
        """Generate HTML table row with proper escaping."""
        return f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>"

    def format_metric_stats(self, stats: Dict[str, float], unit: str = '') -> str:
        """Format statistical metrics into HTML."""
        return f"""
            <tr>
                <td>Mean</td>
                <td>{stats['mean']:.2f}{unit}</td>
            </tr>
            <tr>
                <td>Standard Deviation</td>
                <td>±{stats['std']:.2f}{unit}</td>
            </tr>
            <tr>
                <td>95% Confidence Interval</td>
                <td>±{stats['ci']:.2f}{unit}</td>
            </tr>
            <tr>
                <td>Range</td>
                <td>{stats['min']:.2f} - {stats['max']:.2f}{unit}</td>
            </tr>
        """

    def generate_html_report(self, stability_trends: Dict, 
                           transcriber_performance: Dict, 
                           plots: Dict) -> str:
        """Generate HTML report with analysis results."""
        html = f"""
        <html>
        <head>
            <title>Test Analysis Report v{escape(self.version)}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 20px; border: 1px solid #ccc; }}
                .plot {{ margin: 20px 0; }}
                .stats {{ margin: 10px 0; }}
                table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .warning {{ color: #d73a49; }}
                .success {{ color: #28a745; }}
            </style>
        </head>
        <body>
            <h1>Test Analysis Report</h1>
            <p>Version: {escape(self.version)}</p>
            <p>Analysis period: Last {self.days} days</p>
            
            <div class="section">
                <h2>Stability Test Results</h2>
                <div class="stats">
                    <h3>Success Rate Statistics</h3>
                    <table>
                        {self.format_metric_stats(stability_trends['statistics']['success_rate'], '%')}
                    </table>
                </div>
                <div class="stats">
                    <h3>Test Duration Statistics</h3>
                    <table>
                        {self.format_metric_stats(self.calculate_statistics(stability_trends['test_durations']), ' hours')}
                    </table>
                </div>
                <h3>Common Errors:</h3>
                <table>
                    <tr><th>Error Type</th><th>Count</th></tr>
                    {''.join(self.format_table_row(k, v) for k, v in stability_trends['error_counts'].items())}
                </table>
                <div class="plot">
                    <img src="{plots['stability_success']}" alt="Stability Success Rate">
                </div>
                <div class="plot">
                    <img src="{plots['resource_usage']}" alt="Resource Usage Trends">
                </div>
            </div>
            
            <div class="section">
                <h2>Transcriber Performance</h2>
                <div class="stats">
                    <h3>Accuracy Statistics</h3>
                    <table>
                        {self.format_metric_stats(self.calculate_statistics(transcriber_performance['accuracy_rates']), '%')}
                    </table>
                </div>
                <div class="stats">
                    <h3>Processing Time Statistics</h3>
                    <table>
                        {self.format_metric_stats(self.calculate_statistics(transcriber_performance['processing_times']), ' seconds')}
                    </table>
                </div>
                <h3>Error Distribution:</h3>
                <table>
                    <tr><th>Error Type</th><th>Count</th></tr>
                    {''.join(self.format_table_row(k, v) for k, v in transcriber_performance['error_types'].items())}
                </table>
                <div class="plot">
                    <img src="{plots['transcriber_accuracy']}" alt="Transcription Accuracy Trend">
                </div>
            </div>
            
            <div class="section">
                <h2>Storage Performance</h2>
                {'<div class="plot"><img src="' + escape(plots['storage_performance']) + '" alt="Storage Performance Metrics"></div>' if 'storage_performance' in plots else ''}
                <div class="stats">
                    <h3>Write Latency Statistics</h3>
                    <table>
                        {self.format_metric_stats(stability_trends['statistics']['write_latency'], 's')}
                        <tr>
                            <td>Status</td>
                            <td class="{'success' if stability_trends['statistics']['write_latency']['mean'] < 0.5 else 'warning'}">
                                {escape("✅ Within target" if stability_trends['statistics']['write_latency']['mean'] < 0.5 else "❌ Above target (0.5s)")}
                            </td>
                        </tr>
                    </table>
                </div>
                <div class="stats">
                    <h3>Buffer Usage Statistics</h3>
                    <table>
                        {self.format_metric_stats(stability_trends['statistics']['buffer_usage'], '%')}
                        <tr>
                            <td>Status</td>
                            <td class="{'success' if stability_trends['statistics']['buffer_usage']['mean'] < 80 else 'warning'}">
                                {escape("✅ Within threshold" if stability_trends['statistics']['buffer_usage']['mean'] < 80 else "❌ Above threshold (80%)")}
                            </td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <div class="section">
                <h2>Statistical Analysis</h2>
                <div class="stats">
                    <h3>Resource Usage Statistics</h3>
                    <table>
                        <tr><th>Metric</th><th>CPU Usage</th><th>Memory Usage</th></tr>
                        <tr>
                            <td>Mean</td>
                            <td>{stability_trends['statistics']['cpu_usage']['mean']:.2f}%</td>
                            <td>{stability_trends['statistics']['memory_usage']['mean']:.2f}%</td>
                        </tr>
                        <tr>
                            <td>Standard Deviation</td>
                            <td>±{stability_trends['statistics']['cpu_usage']['std']:.2f}%</td>
                            <td>±{stability_trends['statistics']['memory_usage']['std']:.2f}%</td>
                        </tr>
                        <tr>
                            <td>95% Confidence Interval</td>
                            <td>±{stability_trends['statistics']['cpu_usage']['ci']:.2f}%</td>
                            <td>±{stability_trends['statistics']['memory_usage']['ci']:.2f}%</td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <div class="section">
                <h2>Recommendations</h2>
                <ul>
                    {'<li class="warning">Storage write latency significantly above target (mean: ' + f"{stability_trends['statistics']['write_latency']['mean']:.2f}s ± {stability_trends['statistics']['write_latency']['ci']:.2f}s" + ')</li>' if stability_trends['statistics']['write_latency']['mean'] >= 0.5 else ''}
                    {'<li class="warning">Buffer usage approaching threshold (mean: ' + f"{stability_trends['statistics']['buffer_usage']['mean']:.1f}% ± {stability_trends['statistics']['buffer_usage']['ci']:.1f}%" + ')</li>' if stability_trends['statistics']['buffer_usage']['mean'] >= 70 else ''}
                    {'<li class="warning">Success rate below target (mean: ' + f"{stability_trends['statistics']['success_rate']['mean']*100:.1f}% ± {stability_trends['statistics']['success_rate']['ci']*100:.1f}%" + ')</li>' if stability_trends['statistics']['success_rate']['mean'] < 0.95 else ''}
                    {'<li class="warning">High CPU usage variability (std: ' + f"{stability_trends['statistics']['cpu_usage']['std']:.1f}%" + ')</li>' if stability_trends['statistics']['cpu_usage']['std'] > 10 else ''}
                </ul>
            </div>
            
            <footer>
                <p>Generated on: {escape(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))}</p>
                <p>Report Version: {escape(self.version)}</p>
            </footer>
        </body>
        </html>
        """
        return html
    
    async def cleanup(self):
        """Clean up analyzer resources."""
        try:
            if self.coordinator:
                self.coordinator.update_state(cleanup_started=True)
                # Clean up any temporary files or resources
                for plot_file in self.results_dir.glob('*.png'):
                    try:
                        plot_file.unlink()
                    except Exception as e:
                        logger.error(f"Error cleaning up plot file {plot_file}: {e}")
                self.coordinator.update_state(cleanup_complete=True)
        except Exception as e:
            logger.error(f"Error during analyzer cleanup: {e}")
            if self.coordinator:
                self.coordinator.handle_error(e, "analyzer")

    def run(self, output_file: str):
        """Run the analysis and generate report.
        
        Args:
            output_file: Name of output HTML report file
        """
        try:
            # Load and analyze data
            reports = self.load_test_reports()
            logger.info(f"Loaded {len(reports)} test reports")
            
            logger.info("Analyzing stability trends...")
            stability_trends = self.analyze_stability_trends(reports)
            
            logger.info("Analyzing transcriber performance...")
            transcriber_performance = self.analyze_transcriber_performance(reports)
            
            logger.info("Generating visualization plots...")
            plots = self.generate_plots(stability_trends, transcriber_performance)
            
            logger.info("Generating HTML report...")
            html_report = self.generate_html_report(
                stability_trends, transcriber_performance, plots
            )
            
            # Save report
            output_path = self.results_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_report)
            
            logger.info(f"Analysis complete. Report saved to: {output_path}")
            print(f"Analysis complete. Report saved to: {output_path}")
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}", exc_info=True)
            raise

def main():
    args = parse_args()
    analyzer = ResultAnalyzer(days=args.days)
    analyzer.run(args.output)

if __name__ == '__main__':
    main()
