# Project File Structure

## Overview
This document tracks all files and directories in the Audio Transcriber project, providing descriptions and usage instructions for each component. For detailed policies and standards, refer to the respective policy documents.

## Root Directory
- `requirements.txt` - Project dependencies
- `setup.py` - Package setup and configuration
- `pytest.ini` - Test configuration and markers
- `check_audio_policy.py` - Audio policy verification
- `check_wasapi.py` - WASAPI configuration verification

## Documentation (/docs)
### Development (/docs/development)
- Purpose: Developer documentation and project management
- Structure:
  - `README.md` - Development guidelines and documentation navigation
  - Architecture (/architecture):
    - `architecture.md` - System architecture and design diagrams
    - `component_relationships.md` - Component interaction documentation
  - Implementation (/implementation):
    - `core_stability.md` - Thread safety and stability implementation
    - `transcription.md` - Transcription system implementation
  - Status (/status):
    - `PROJECT_STATUS.md` - Comprehensive project status and roadmap
    - `STATUS_SUMMARY.md` - Project health dashboard and metrics
  - Tracking (/tracking):
    - `file_tracker.md` - Project file structure documentation
    - `CHANGELOG.md` - Version history and change tracking
  - Core Documentation:
    - `buffer_management.md` - Buffer management system documentation
    - `performance.md` - Performance tuning and optimization guide
    - `structure_improvements.md` - System structure improvements
    - `transcription_display.md` - Real-time display system
    - `troubleshooting.md` - System troubleshooting procedures

### Archive
- Purpose: Historical documentation
- Contents:
  - `2024_02/` - February 2024 Archive
    - `original_roadmap.md` - Original project specifications (READ ONLY)
  - `dev_api.txt` - Legacy API documentation
  - `dev_prerequisites.md` - Previous setup requirements
  - `dev_setup_checks.txt` - Previous system checks

## Source Code (/src/audio_transcriber)
### Core Components
- `__init__.py` - Package initialization and version information
- `alert_system.py` - Alert system implementation
- `analyze_results.py` - Analysis system implementation
- `audio_capture.py` - WASAPI audio capture implementation
- `audio_transcriber.py` - Core transcription logic
- `buffer_manager.py` - ResourcePool-based buffer management
- `cleanup_coordinator.py` - Thread-safe cleanup coordination
- `component_coordinator.py` - Enhanced component lifecycle and state management:
  * Channel-aware component management
  * Enhanced cleanup coordination with staged phases
  * Thread failure tracking and recovery
  * State validation with retry mechanism
  * Resource allocation validation and tracking
  * Health check validation system
  * State history tracking with error context
  * Dependency management with validation
  * Performance metrics collection
  * Comprehensive error handling
- `main.py` - Application entry point
- `monitoring_coordinator.py` - Enhanced performance monitoring system:
  * Channel-specific metrics tracking
  * Enhanced error context preservation
  * Performance metrics collection
  * Resource state monitoring
  * Component health tracking
  * Thread failure detection
  * Staged cleanup coordination
  * Real-time performance analysis
  * Comprehensive error handling
  * Detailed logging with context
- `recovery_logger.py` - Recovery process logging
- `resource_pool.py` - Tiered buffer pool (4KB/64KB/1MB) implementation
- `signal_processor.py` - ResourcePool-based audio processing
- `speaker_isolation.py` - ResourcePool-integrated speaker isolation
- `state_machine.py` - Enhanced state management system:
  * Channel-specific states for granular control
  * Performance metrics tracking with timing
  * Coordinator validation with retry mechanism
  * Enhanced error handling and context
  * Resource pool integration
  * Component health validation
  * Staged cleanup coordination
  * State transition validation
  * Rollback mechanisms
  * Comprehensive logging
- `storage_manager.py` - Thread-safe storage management
- `system_verifier.py` - System verification utilities
- `transcription_formatter.py` - Transcription formatting
- `transcription_manager.py` - Transcription coordination
- `wasapi_monitor.py` - WASAPI device monitoring
- `whisper_transcriber.py` - Whisper API integration
- `windows_manager.py` - Windows API integration

### GUI Components (/src/audio_transcriber/gui)
- `__init__.py` - GUI module initialization
- `app.py` - Application setup and version management
- `config.json` - GUI configuration
- `main_window.py` - Main window implementation
- `resources/` - GUI resources and assets

### Test Configuration (/src/audio_transcriber/test_config)
- `__init__.py` - Test config initialization
- `device_config.py` - Device configuration utilities
- `scenario_generator.py` - Test scenario generation

## Testing (/tests)
### Test Infrastructure
- `TEST_POLICY.md` - Test output management and retention policies
- `TEST_COVERAGE_ANALYSIS.md` - Coverage analysis and requirements
- `conftest.py` - PyTest configuration
- `run_tests.py` - Test execution script
- `test_config.py` - Test configuration
- `test_core.py` - Core functionality tests
- `test_recovery_logger.py` - Recovery logger tests

### Core Tests (/tests/core)
- Contains comprehensive unit tests for all core components:
  - `test_alert_system.py` & `test_alert_system_dynamic.py` - Alert system tests
  - `test_analysis.py` - Analysis system tests
  - `test_audio_capture.py` & `test_audio_capture_advanced.py` - Audio capture tests
  - `test_buffer_manager.py` & `test_buffer_manager_atomic.py` - ResourcePool buffer tests
  - `test_cleanup.py` - Cleanup system tests
  - `test_component_coordinator.py` - Component coordination tests
  - `test_config.py` - Configuration system tests
  - `test_monitoring.py` - Monitoring system tests
  - `test_resource_pool.py` - Tiered buffer pool tests
  - `test_signal_processor.py` & `test_signal_processor_memory.py` - ResourcePool processing tests
  - `test_speaker_isolation.py` - ResourcePool isolation tests
  - `test_state_machine.py` - State management tests
  - `test_storage_manager.py` - Storage management tests
  - `test_thread_safety.py` - Thread safety tests
  - `test_transcription_formatter.py` - Transcription formatting tests
  - `test_transcription_manager.py` - Transcription management tests
  - `test_whisper_transcriber.py` - Whisper integration tests
  - `test_windows_manager.py` - Windows API integration tests

### Integration Tests (/tests/integration)
- `test_audio_processing_chain.py` - Audio pipeline tests
- `test_real_devices.py` - Hardware integration tests
- `test_system_integration.py` - Full system integration
- `test_thread_safety.py` - Thread safety validation
- `test_transcription_display.py` - Display integration
- `test_wasapi_stability.py` - WASAPI stability tests

### Stability Tests (/tests/stability)
- Long-running stability test framework
- Performance degradation detection
- Resource leak detection

### Test Results (/tests/results)
- `analysis.log` - Test analysis logs
- `test_report_[timestamp].json` - Current test reports
- Archives:
  - Historical test reports (JSON format)
  - Stability test results
  - Transcriber test results
- Logs:
  - Component test logs
  - Test recovery logs

### Test Utilities (/tests/utilities)
- `base.py` - Base test classes
- `cleanup.py` - Test cleanup utilities
- `mocks.py` - Mock objects and utilities
- `reporting.py` - Test result reporting

## Change Management (/changes)
### Documentation
- `CHANGELOG.md` - Version history and changes (Current: v0.5.0)
- `README.md` - Project rules and structure requirements

### Templates
- `feature.md` - New feature documentation template
- `bugfix.md` - Bug fix documentation template
- `compatibility.md` - Compatibility change template

### Bug Tracking (/changes/bugs)
- `Bug_Dependencies.md` - Bug dependency tracking

#### Archived Bugs (/changes/bugs/archive)
- `Alert_System_Bug.md` - Alert system improvements
- `Analysis_System_Bug.md` - Analysis system optimization
- `Architecture_Bug.md` - Architecture improvements
- `Audio_Capture_Bug.md` - Audio capture stability
- `Audio_Processing_Chain_Bug.md` - Processing chain optimization
- `Audio_Processing_Fixes.md` - Audio processing improvements
- `Audioop_Import_Bug.md` - Import system fixes
- `Buffer_Manager_Fix.md` - Buffer management improvements
- `Core_Application_Bug.md` - Core application stability
- `CPU_Performance_Bug.md` - CPU utilization optimization
- `Python13_Compatibility_Bug.md` - Python 13 compatibility
- `Signal_Processing_Bug.md` - Signal processing improvements
- `Storage_Performance_Bug.md` - Storage performance optimization
- `Test_Coverage_Improvements.md` - Test coverage enhancements
- `Test_Framework_Bug.md` - Test framework stability
- `Thread_Safety_Bug.md` - Thread safety improvements
- `WASAPI_Stability_Bug.md` - WASAPI stability fixes
- `Windows11_API_Bug.md` - Windows 11 compatibility

## Data Management
### Recordings
- `BACKUP_POLICY.md` - Backup retention and management policies
- Emergency Backup:
  - `emergency_backup/` - Emergency backup storage with timestamped files
- Logs:
  - `logs/` - Recording session logs with timestamps

### System Logs
- `analytics/` - Performance monitoring data
- `debug/` - Debug information logs
- `recovery/` - Recovery operation logs

## Usage Instructions

### For Developers
1. Review requirements.txt for dependencies
2. Follow development guidelines in docs/development/README.md
3. Use appropriate templates from /changes/templates
4. Run tests using tests/run_tests.py
5. Follow backup and test policies

### For Documentation
1. Never modify original_roadmap.md
2. Keep documentation in appropriate directories
3. Update file_tracker.md when adding/moving files
4. Follow policy documents for backups and tests

### For Testing
1. Store all test outputs in tests/results/
2. Run cleanup_test_outputs.py regularly
3. Use analyze_results.py for trend analysis
4. Follow TEST_POLICY.md guidelines

### For Backup Management
1. Follow BACKUP_POLICY.md guidelines
2. Use emergency_backup for crash recovery
3. Monitor backup size limits
4. Follow retention policies

## Notes
- All paths are relative to project root
- Version information in __init__.py is authoritative
- Follow policy documents for standards
- Keep directory structure clean and organized
