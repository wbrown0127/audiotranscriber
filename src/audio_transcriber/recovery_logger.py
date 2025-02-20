"""
COMPONENT_NOTES:
{
    "name": "RecoveryLogger",
    "type": "Core Component",
    "description": "Recovery logging system that manages recovery process logging, analytics collection, and debugging tools with session management",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                RL[RecoveryLogger] --> RA[RecoveryAttempt]
                RL --> RM[RecoveryMetrics]
                RL --> AC[AnalyticsCache]
                RL --> SM[SessionManager]
                RA --> RM
                RA --> CS[CleanupStatus]
                RM --> RU[ResourceUsage]
                AC --> SA[StatisticalAnalysis]
                AC --> TT[TriggerTracking]
                AC --> ST[StateTransitions]
        ```",
        "dependencies": {
            "RecoveryAttempt": "Recovery attempt tracking",
            "RecoveryMetrics": "Performance metrics",
            "AnalyticsCache": "Analytics storage",
            "SessionManager": "Session lifecycle",
            "CleanupStatus": "Cleanup tracking",
            "ResourceUsage": "System resource tracking",
            "StatisticalAnalysis": "Analytics processing",
            "TriggerTracking": "Recovery trigger analysis",
            "StateTransitions": "State change tracking"
        }
    },
    "notes": [
        "Manages recovery process logging",
        "Collects and analyzes recovery metrics",
        "Tracks system resource usage",
        "Provides debugging tools",
        "Handles session management",
        "Supports analytics generation"
    ],
    "usage": {
        "examples": [
            "logger = RecoveryLogger(base_path)",
            "logger.start_session()",
            "await logger.log_recovery_attempt(trigger, states, metrics, cleanup)",
            "logger.end_session()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "aiofiles",
            "asyncio",
            "psutil",
            "statistics"
        ],
        "system": {
            "storage": "Space for log files",
            "permissions": "Write access to log directories"
        }
    },
    "performance": {
        "execution_time": "Async I/O for minimal blocking",
        "resource_usage": [
            "Light disk I/O for logging",
            "Minimal memory for analytics cache",
            "Efficient log rotation",
            "Optimized state tracking"
        ]
    }
}
"""

import json
import logging
import psutil
import aiofiles
import asyncio
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class RecoveryMetrics:
    """Metrics collected during recovery process."""
    start_time: float
    end_time: float
    duration: float
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    success: bool
    error: Optional[str] = None

@dataclass
class RecoveryAttempt:
    """Details of a recovery attempt."""
    attempt_id: str
    timestamp: float
    trigger: str
    states: List[Dict[str, Any]]
    metrics: RecoveryMetrics
    cleanup_status: Dict[str, Any]

class RecoveryLogger:
    """
    Manages recovery process logging, analytics, and debugging tools.
    """
    
    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path)
        self.logger = logging.getLogger("RecoveryLogger")
        
        # Setup subdirectories
        self.logs_dir = self.base_path / "logs"
        self.recovery_log_dir = self.logs_dir / "recovery"
        self.analytics_dir = self.logs_dir / "analytics"
        self.debug_dir = self.logs_dir / "debug"
        
        # Create subdirectories
        for directory in [self.logs_dir, self.recovery_log_dir, self.analytics_dir, self.debug_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Recovery attempt history
        self.attempts: List[RecoveryAttempt] = []
        
        # Analytics cache
        self._analytics_cache: Dict[str, Any] = {}
        
        # Session tracking
        self._current_session_id: Optional[str] = None
        self._session_start_time: Optional[float] = None
        
    def start_session(self):
        """Start a new recovery logging session."""
        self._current_session_id = f"session_{int(datetime.now().timestamp())}"
        self._session_start_time = datetime.now().timestamp()
        self.logger.info(f"Started recovery logging session: {self._current_session_id}")
        
    def end_session(self):
        """End the current recovery logging session."""
        if self._current_session_id and self._session_start_time:
            duration = datetime.now().timestamp() - self._session_start_time
            self.logger.info(
                f"Ended recovery logging session: {self._current_session_id} "
                f"(duration: {duration:.2f}s)"
            )
            self._current_session_id = None
            self._session_start_time = None
            
    def get_last_recovery_status(self) -> str:
        """Get the status of the last recovery attempt."""
        if not self.attempts:
            return "no_attempts"
        return "success" if self.attempts[-1].metrics.success else "failed"
        
    def _generate_attempt_id(self) -> str:
        """Generate unique ID for recovery attempt."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        attempt_num = len(self.attempts) + 1
        return f"recovery_{timestamp}_{attempt_num}"
        
    async def log_recovery_attempt(self, trigger: str,
                                 states: List[Dict[str, Any]],
                                 metrics: RecoveryMetrics,
                                 cleanup_status: Dict[str, Any]):
        """Log a recovery attempt with all associated data."""
        attempt = RecoveryAttempt(
            attempt_id=self._generate_attempt_id(),
            timestamp=datetime.now().timestamp(),
            trigger=trigger,
            states=states,
            metrics=metrics,
            cleanup_status=cleanup_status
        )
        
        self.attempts.append(attempt)
        
        # Write to log file
        log_file = self.recovery_log_dir / f"{attempt.attempt_id}.json"
        
        try:
            async with aiofiles.open(log_file, 'w') as f:
                await f.write(json.dumps(asdict(attempt), indent=2))
            
            self.logger.info(
                f"Recovery attempt logged: {attempt.attempt_id}"
            )
            
            # Update analytics
            await self._update_analytics()
            
        except Exception as e:
            self.logger.error(f"Failed to log recovery attempt: {str(e)}")
            
    async def _update_analytics(self):
        """Update recovery analytics."""
        if not self.attempts:
            return
            
        analytics = {
            'total_attempts': len(self.attempts),
            'success_rate': self._calculate_success_rate(),
            'average_duration': self._calculate_average_duration(),
            'resource_usage': self._calculate_resource_usage(),
            'common_triggers': self._analyze_triggers(),
            'state_transitions': self._analyze_state_transitions(),
            'timestamp': datetime.now().timestamp()
        }
        
        # Cache analytics
        self._analytics_cache = analytics
        
        # Write to file
        analytics_file = self.analytics_dir / f"recovery_analytics_{datetime.now():%Y%m%d}.json"
        
        try:
            async with aiofiles.open(analytics_file, 'w') as f:
                await f.write(json.dumps(analytics, indent=2))
        except Exception as e:
            self.logger.error(f"Failed to write analytics: {str(e)}")
            
    def _calculate_success_rate(self) -> float:
        """Calculate recovery success rate."""
        if not self.attempts:
            return 0.0
        successful = sum(1 for attempt in self.attempts 
                        if attempt.metrics.success)
        return (successful / len(self.attempts)) * 100
        
    def _calculate_average_duration(self) -> float:
        """Calculate average recovery duration."""
        if not self.attempts:
            return 0.0
        durations = [attempt.metrics.duration for attempt in self.attempts]
        return statistics.mean(durations)
        
    def _calculate_resource_usage(self) -> Dict[str, float]:
        """Calculate average resource usage during recovery."""
        if not self.attempts:
            return {'cpu': 0.0, 'memory': 0.0, 'disk': 0.0}
            
        cpu_usage = statistics.mean(
            attempt.metrics.cpu_usage for attempt in self.attempts
        )
        memory_usage = statistics.mean(
            attempt.metrics.memory_usage for attempt in self.attempts
        )
        disk_usage = statistics.mean(
            attempt.metrics.disk_usage for attempt in self.attempts
        )
        
        return {
            'cpu': cpu_usage,
            'memory': memory_usage,
            'disk': disk_usage
        }
        
    def _analyze_triggers(self) -> Dict[str, int]:
        """Analyze common recovery triggers."""
        triggers: Dict[str, int] = {}
        for attempt in self.attempts:
            triggers[attempt.trigger] = triggers.get(attempt.trigger, 0) + 1
        return triggers
        
    def _analyze_state_transitions(self) -> Dict[str, Dict[str, int]]:
        """Analyze state transition patterns."""
        transitions: Dict[str, Dict[str, int]] = {}
        
        for attempt in self.attempts:
            for i in range(len(attempt.states) - 1):
                current = attempt.states[i]['state']
                next_state = attempt.states[i + 1]['state']
                
                if current not in transitions:
                    transitions[current] = {}
                transitions[current][next_state] = \
                    transitions[current].get(next_state, 0) + 1
                    
        return transitions
        
    async def create_state_dump(self, attempt_id: str) -> str:
        """Create a detailed state dump for debugging."""
        attempt = next(
            (a for a in self.attempts if a.attempt_id == attempt_id),
            None
        )
        if not attempt:
            raise ValueError(f"Recovery attempt not found: {attempt_id}")
            
        dump_file = self.debug_dir / f"state_dump_{attempt_id}.json"
        
        dump_data = {
            'attempt': asdict(attempt),
            'analytics': {
                'success_rate': self._calculate_success_rate(),
                'average_duration': self._calculate_average_duration(),
                'resource_usage': self._calculate_resource_usage()
            },
            'system_state': await self._capture_system_state(),
            'timestamp': datetime.now().timestamp()
        }
        
        try:
            async with aiofiles.open(dump_file, 'w') as f:
                await f.write(json.dumps(dump_data, indent=2))
            return dump_file
        except Exception as e:
            self.logger.error(f"Failed to create state dump: {str(e)}")
            raise
            
    async def _capture_system_state(self) -> Dict[str, Any]:
        """Capture current system state for debugging."""
        try:
            process = psutil.Process()
            return {
                'cpu_percent': process.cpu_percent(),
                'memory_info': process.memory_info()._asdict(),
                'open_files': [f.path for f in process.open_files()],
                'threads': process.num_threads(),
                'status': process.status(),
                'timestamp': datetime.now().timestamp()
            }
        except Exception as e:
            self.logger.error(f"Failed to capture system state: {str(e)}")
            return {'error': str(e)}
            
    def get_analytics(self) -> Dict[str, Any]:
        """Get current recovery analytics."""
        return self._analytics_cache
        
    async def get_attempt_details(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific recovery attempt."""
        log_file = self.recovery_log_dir / f"{attempt_id}.json"
        
        try:
            if not log_file.exists():
                return None
                
            async with aiofiles.open(log_file, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            self.logger.error(
                f"Failed to read attempt details: {str(e)}"
            )
            return None
            
    async def cleanup_old_logs(self, days: int = 30):
        """Clean up old recovery logs."""
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        
        for directory in [self.recovery_log_dir, 
                         self.analytics_dir,
                         self.debug_dir]:
            try:
                for filepath in directory.glob('*'):
                    if filepath.stat().st_ctime < cutoff:
                        filepath.unlink()
                        self.logger.info(f"Removed old log: {filepath}")
            except Exception as e:
                self.logger.error(
                    f"Failed to cleanup directory {directory}: {str(e)}"
                )
