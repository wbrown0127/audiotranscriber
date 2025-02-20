"""
Utility script for managing test outputs and cleaning up test artifacts.
"""
import os
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from typing_extensions import Tuple  # Updated to use typing_extensions for Python 3.13 compatibility

class CleanupUtility:
    """Manages cleanup of test outputs and artifacts."""
    
    def __init__(self, test_root: str = None):
        self.test_root = Path(test_root) if test_root else Path(__file__).parent.parent
        self.logger = logging.getLogger("test_cleanup")
        
        # Configure retention periods
        self.retention_periods = {
            "results": timedelta(days=30),    # Keep test results for 30 days
            "logs": timedelta(days=7),        # Keep logs for 7 days
            "stability": timedelta(days=3),    # Keep stability test outputs for 3 days
            "emergency": timedelta(hours=24)   # Keep emergency backups for 24 hours
        }
    
    def cleanup_old_results(self) -> Tuple[int, List[str]]:
        """Clean up old test results and return count of removed files."""
        removed_count = 0
        removed_files = []
        
        # Clean up test results
        results_dir = self.test_root / "results"
        if results_dir.exists():
            # Handle transcriber tests - keep only 10 most recent
            transcriber_dirs = sorted(
                [d for d in results_dir.glob("test_transcriber_*")
                 if d.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            dirs_to_remove = transcriber_dirs[10:]
            for dir_path in dirs_to_remove:
                try:
                    shutil.rmtree(dir_path)
                    removed_count += 1
                    removed_files.append(str(dir_path))
                    self.logger.info(f"Removed transcriber test directory: {dir_path}")
                except Exception as e:
                    self.logger.error(f"Failed to remove {dir_path}: {e}")
            
            # Clean up other test results
            removed = self._cleanup_directory(
                results_dir,
                self.retention_periods["results"],
                exclude_patterns=["*.html", "test_transcriber_*"]  # Exclude transcriber tests and HTML reports
            )
            removed_count += len(removed)
            removed_files.extend(removed)
            
        # Clean up logs
        logs_dir = results_dir / "logs"
        if logs_dir.exists():
            removed = self._cleanup_directory(logs_dir, self.retention_periods["logs"])
            removed_count += len(removed)
            removed_files.extend(removed)
            
        return removed_count, removed_files
    
    def cleanup_stability_results(self) -> Tuple[int, List[str]]:
        """Clean up old stability test results, keeping only the 5 most recent."""
        removed_count = 0
        removed_files = []
        
        stability_dirs = sorted(
            [d for d in (self.test_root / "results").glob("test_stability_*")
             if d.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        # Keep only the 5 most recent directories
        dirs_to_remove = stability_dirs[5:]
        for stability_dir in dirs_to_remove:
            try:
                shutil.rmtree(stability_dir)
                removed_count += 1
                removed_files.append(str(stability_dir))
                self.logger.info(f"Removed stability test directory: {stability_dir}")
            except Exception as e:
                self.logger.error(f"Failed to remove {stability_dir}: {e}")
        
        return removed_count, removed_files
    
    def cleanup_emergency_backups(self) -> Tuple[int, List[str]]:
        """Clean up old emergency backup files."""
        removed_count = 0
        removed_files = []
        
        # Clean emergency backups in test results
        for backup_dir in self.test_root.rglob("emergency_backup"):
            if backup_dir.is_dir():
                removed = self._cleanup_directory(
                    backup_dir,
                    self.retention_periods["emergency"],
                    pattern="emergency_*.tmp"
                )
                removed_count += len(removed)
                removed_files.extend(removed)
        
        return removed_count, removed_files
    
    def _cleanup_directory(self, 
                          directory: Path,
                          max_age: timedelta,
                          pattern: str = "*",
                          exclude_patterns: List[str] = None) -> List[str]:
        """Clean up files in directory older than max_age."""
        removed_files = []
        exclude_patterns = exclude_patterns or []
        
        try:
            for item in directory.glob(pattern):
                # Skip excluded patterns
                if any(item.match(pat) for pat in exclude_patterns):
                    continue
                    
                if self._is_older_than(item, max_age):
                    try:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                        removed_files.append(str(item))
                        self.logger.info(f"Removed: {item}")
                    except Exception as e:
                        self.logger.error(f"Failed to remove {item}: {e}")
        except Exception as e:
            self.logger.error(f"Error cleaning directory {directory}: {e}")
        
        return removed_files
    
    def _is_older_than(self, path: Path, age: timedelta) -> bool:
        """Check if path is older than specified age."""
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            return datetime.now() - mtime > age
        except Exception as e:
            self.logger.error(f"Error checking age of {path}: {e}")
            return False

    def get_test_dirs(self, pattern: str) -> List[Path]:
        """Get list of test directories matching pattern."""
        results_dir = self.test_root / "results"
        if not results_dir.exists():
            return []
        return sorted(results_dir.glob(pattern))
    
    def run_cleanup(self, dry_run: bool = False) -> dict:
        """Run all cleanup operations and return summary."""
        self.logger.info("Starting test cleanup" + (" (DRY RUN)" if dry_run else ""))
        
        if dry_run:
            # Just log what would be removed
            results_count, results_files = self._simulate_cleanup(
                self.cleanup_old_results)
            stability_count, stability_files = self._simulate_cleanup(
                self.cleanup_stability_results)
            emergency_count, emergency_files = self._simulate_cleanup(
                self.cleanup_emergency_backups)
        else:
            # Actually perform cleanup
            results_count, results_files = self.cleanup_old_results()
            stability_count, stability_files = self.cleanup_stability_results()
            emergency_count, emergency_files = self.cleanup_emergency_backups()
        
        summary = {
            "test_results_removed": results_count,
            "stability_dirs_removed": stability_count,
            "emergency_backups_removed": emergency_count,
            "total_items_removed": results_count + stability_count + emergency_count,
            "removed_files": {
                "results": results_files,
                "stability": stability_files,
                "emergency": emergency_files
            }
        }
        
        self.logger.info(f"Cleanup complete. Removed {summary['total_items_removed']} items.")
        return summary
    
    def _simulate_cleanup(self, cleanup_func) -> Tuple[int, List[str]]:
        """Simulate cleanup operation for dry run."""
        try:
            count, files = cleanup_func()
            for file in files:
                self.logger.info(f"Would remove: {file}")
            return count, files
        except Exception as e:
            self.logger.error(f"Error simulating cleanup: {e}")
            return 0, []

def main():
    """Command line interface for cleanup utility."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean up test outputs and artifacts")
    parser.add_argument("--dry-run", action="store_true",
                      help="Show what would be removed without actually removing")
    parser.add_argument("--test-root", type=str,
                      help="Root directory of test files (default: parent of this script)")
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Run cleanup
    cleanup = CleanupUtility(args.test_root)
    summary = cleanup.run_cleanup(dry_run=args.dry_run)
    
    # Print summary
    print("\nCleanup Summary:")
    print(f"Test Results Removed: {summary['test_results_removed']}")
    print(f"Stability Directories Removed: {summary['stability_dirs_removed']}")
    print(f"Emergency Backups Removed: {summary['emergency_backups_removed']}")
    print(f"Total Items Removed: {summary['total_items_removed']}")

if __name__ == "__main__":
    main()
