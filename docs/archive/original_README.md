# Audio Transcriber Development Guide

## Overview
This document serves as the single source of truth for the Audio Transcriber project, consolidating development guidelines, project structure, and best practices.

## Quick Links
- [CHANGELOG.md](../../changes/CHANGELOG.md) - Version history and changes
- [file_tracker.md](../../file_tracker.md) - Comprehensive file structure and usage guide
- [phase3_transcription.md](phase3_transcription.md) - Current phase details
- [architecture.md](architecture.md) - System architecture documentation
- [phase2_core_stability.md](phase2_core_stability.md) - Previous phase details

## Table of Contents
1. [Development Standards](#development-standards)
2. [Project Structure](#project-structure)
3. [Best Practices](#best-practices)
4. [System Requirements](#system-requirements)
5. [Development Environment](#development-environment)
6. [API Configuration](#api-configuration)
7. [Project Setup](#project-setup)
8. [Testing](#testing)
9. [Troubleshooting](#troubleshooting)
10. [Phase Completion Requirements](#phase-completion-requirements)
11. [Known Issues and Tracking](#known-issues-and-tracking)

## Development Standards

### Code Organization Standards
1. **Path Handling**
   - Use pathlib.Path for all path operations
   - Define paths in central configuration
   - Use relative paths from project root
   - Example:
     ```python
     from pathlib import Path
     
     # Good
     base_path = Path(__file__).parent.parent
     config_path = base_path / "config" / "settings.json"
     
     # Bad
     config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
     ```

2. **Import Standards**
   - Use absolute imports from project root
   - Group imports in order: stdlib, third-party, local
   - Avoid circular dependencies
   - Example:
     ```python
     # Standard library
     import asyncio
     from typing import Optional
     
     # Third-party
     import numpy as np
     from PySide6.QtCore import Qt
     
     # Local
     from audio_transcriber.core import StateMachine
     from audio_transcriber.utils import Logger
     ```

3. **File Operations**
   - Use async operations with aiofiles
   - Always use context managers
   - Implement consistent error handling
   - Example:
     ```python
     async def save_data(data: bytes, filepath: Path):
         try:
             async with aiofiles.open(filepath, 'wb') as f:
                 await f.write(data)
                 await f.flush()
         except IOError as e:
             logger.error(f"Failed to save data: {e}")
             raise StorageError(f"Write failed: {e}")
     ```

4. **Thread Management**
   - Use coordinator for thread registration
   - Implement consistent cleanup protocol
   - Standardize monitoring intervals
   - Example:
     ```python
     def __init__(self):
         self.coordinator.register_thread()
         try:
             self.setup_resources()
         except Exception:
             self.coordinator.unregister_thread()
             raise
     ```

5. **Configuration Management**
   - Use central Config class
   - Define all constants in config
   - Implement validation
   - Example:
     ```python
     from dataclasses import dataclass
     
     @dataclass
     class AudioConfig:
         sample_rate: int = 16000
         channels: int = 2
         buffer_size: int = 480
         
         def validate(self):
             assert self.sample_rate in [8000, 16000, 44100, 48000]
             assert self.channels in [1, 2]
             assert 0 < self.buffer_size <= 4096
     ```

## Project Structure

### Core Organization
```
audio_transcriber/
├── src/                      # Source code
│   └── audio_transcriber/    # Main package
│       # Critical Components
│       ├── __init__.py         # Package initialization (Critical)
│       ├── main.py            # Application entry point (Critical)
│       ├── audio_capture.py    # WASAPI audio capture (Critical)
│       ├── audio_transcriber.py # Core transcription (Critical)
│       ├── buffer_manager.py   # Thread-safe buffers (Critical)
│       ├── signal_processor.py # Audio processing (Critical)
│       ├── storage_manager.py  # File management (Critical)
│       ├── transcription_formatter.py # Real-time display (Critical)
│       ├── wasapi_monitor.py   # WASAPI stability (Critical)
│       ├── windows_manager.py  # Windows integration (Critical)
│       # Support Components
│       ├── alert_system.py    # Performance alerts (Support)
│       ├── cleanup_coordinator.py # Resource cleanup (Support)
│       ├── monitoring_coordinator.py # Performance tracking (Support)
│       ├── recovery_logger.py  # Recovery tracking (Support)
│       ├── state_machine.py    # Thread-safe state (Support)
│       └── gui/               # GUI components
│           ├── __init__.py    # GUI initialization (Critical)
│           ├── app.py         # Application setup (Critical)
│           └── main_window.py # Main window UI (Critical)
├── docs/                     # Documentation
│   ├── development/         # Developer docs (Critical)
│   │   ├── README.md       # This file (Critical)
│   │   ├── architecture.md # System design (Critical)
│   │   ├── performance.md  # Tuning guide (Critical)
│   │   ├── phase2_core_stability.md # Phase 2 details (Temporary)
│   │   └── troubleshooting.md # Debug guide (Critical)
│   └── archive/            # Historical docs (Reference)
├── tests/                   # Test suite
│   # Core Test Files (Critical)
│   ├── conftest.py         # Test configuration
│   ├── run_tests.py        # Test runner
│   ├── test_core.py        # Core functionality
│   ├── test_buffer_manager.py # Buffer management
│   ├── test_cleanup_coordination.py # Cleanup system
│   ├── test_real_devices.py # Hardware testing
│   ├── test_recovery_logger.py # Recovery system
│   ├── test_stability.py   # Long-term stability
│   ├── test_state_machine.py # State management
│   ├── test_system_integration.py # Integration
│   ├── test_thread_safety.py # Thread safety
│   ├── test_wasapi_stability.py # WASAPI testing
│   ├── verify_system_restart.py # System verification
│   # Test Support (Support)
│   ├── test_config/       # Test configuration
│   │   ├── device_config.py # Device setup
│   │   └── scenario_generator.py # Test scenarios
│   └── results/           # Test outputs (Temporary)
├── changes/                # Change tracking
│   ├── CHANGELOG.md       # Version history (Critical)
│   ├── README.md         # Change guidelines (Critical)
│   ├── bugs/             # Bug tracking (Critical)
│   │   ├── Audio_Processing_Fixes.md
│   │   ├── CPU_Performance_Bug.md
│   │   ├── Storage_Performance_Bug.md
│   │   ├── Windows11_API_Bug.md
│   │   └── archive/     # Resolved bugs (Reference)
│   └── templates/        # Change templates (Critical)
├── recordings/            # Audio data
│   ├── backup/           # Standard backups (Critical)
│   ├── emergency_backup/ # Emergency saves (Critical)
│   └── logs/            # Recording logs (Critical)
├── logs/                 # System logs
│   ├── analytics/       # Performance data (Critical)
│   ├── debug/          # Debug information (Support)
│   └── recovery/       # Recovery logs (Critical)
# Configuration Files
├── setup.py             # Package setup (Critical)
├── requirements.txt     # Dependencies (Critical)
├── check_wasapi.py     # WASAPI validation (Support)
├── check_audio_policy.py # Audio policy validation (Support)
└── original_roadmap.md  # Original specifications (Reference)
```

### Directory Standards
1. **Source Code**
   - All code under src/audio_transcriber/
   - One component per file
   - Clear component responsibilities
   - Proper package structure

2. **Documentation**
   - Current docs in docs/development/
   - Historical docs in docs/archive/
   - One primary README per directory
   - Architecture diagrams in docs/development/

3. **Testing**
   - All tests under tests/
   - Test outputs in tests/results/
   - One test file per component
   - Clear test naming convention

4. **Change Management**
   - All changes documented in changes/
   - Use templates from changes/templates/
   - Follow semantic versioning
   - Track all modifications

5. **Data Management**
   - Recordings in recordings/
   - Structured backup hierarchy
   - Clear retention policies
   - Proper cleanup procedures

## Best Practices

### Development Workflow
1. **Version Control**
   - One feature per branch
   - Clear commit messages
   - Regular integration
   - Version tags for releases

2. **Code Style**
   - Follow PEP 8
   - Use type hints
   - Document public APIs
   - Clear error handling

3. **Testing Strategy**
   - Write tests first
   - Mock external dependencies
   - Test edge cases
   - Verify thread safety

4. **Documentation**
   - Keep README.md updated
   - Document all changes
   - Clear API documentation
   - Usage examples

5. **Performance**
   - Regular profiling
   - Memory monitoring
   - I/O optimization
   - Thread coordination

### System Requirements

### Hardware Requirements
- **CPU**: i7-4790K or better
  - ✓ AVX2 instruction support verified
  - 🟡 Below original i5-8250U spec but sufficient for operations
  - ✓ Adequate for real-time transcription
- **Memory**: 4GB DDR4 RAM minimum
  - 2GB reserved for dedicated audio buffers
  - 1GB for transcription processing
  - Remaining for system and application overhead
- **Storage**: SATA drives (NVMe not required)
  - 🟡 Slightly higher latency, negligible for small files
  - Minimum 100MB free space
  - Async I/O optimization implemented

### Audio Interface
- **Sound Card**: Realtek or compatible
  - Must support WASAPI loopback mode
  - 16-bit/16kHz capability required
- **VB-Cable Virtual Audio Device**
  - ✓ Free version verified compatible
  - Essential for channel isolation

### Operating System
- **Windows**: Windows 11 or Windows 10 22H2
  - Compatible with standard and N/KN editions
  - All latest Windows updates installed
  - MMCSS (Multimedia Class Scheduler Service) enabled
  - Windows Media Foundation support required

## Development Environment

### Required Software
- **Python 3.13.1**
  - 🟡 Modified but Compatible
  - Using audioop-lts for Python 3.13 compatibility
- **Visual Studio Build Tools 2022**
  - Windows SDK 10.0.19041.0 or newer
- **Git** for version control
- **WiX Toolset** v3.11.2+ (for MSIX packaging)

### Python Packages
```bash
# Current Dependencies
PySide6==6.5.3        # GUI Framework
openai>=1.3.6         # API Integration
numpy>=1.24.3         # Signal Processing
audioop-lts>=0.2.1    # Audio Processing (Temporary)
pyaudiowpatch>=0.2.12 # WASAPI Integration
pywin32==306          # Windows Integration
comtypes==1.2.0       # COM Interface
aiofiles>=23.2.1      # Async file operations 
psutil>=5.9.6         # System monitoring
webrtcvad>=2.0.10     # Voice Activity Detection
```

### Upcoming Changes
1. Signal Processing Migration
   - Windows Media Foundation integration
   - webrtcvad implementation
   - Hardware acceleration setup

2. File Management Implementation
   - Custom buffer system with thread-safe operations
   - Emergency backup protocol with rotation/cleanup
   - Integrated performance monitoring (ref: Storage_Performance_Bug.md)
   - State machine-integrated recovery system

3. GUI Implementation
   - PySide6 + QtWinExtras setup
   - Native Windows controls
   - Hardware-accelerated rendering

4. Deployment System
   - MSIX packaging configuration
   - WiX installer setup
   - Automatic updates implementation

## API Configuration

### OpenAI Whisper Integration
The system uses OpenAI's Whisper API for audio transcription with the following features:
- Voice Activity Detection (VAD) for cost optimization
- Speaker isolation and tracking
- Rate limiting (50 requests/minute)
- Async processing with retry logic
- Performance monitoring and cost tracking

```python
# Example Configuration
WHISPER_CONFIG = {
    "model": "whisper-1",
    "max_retries": 3,
    "rate_limit_per_min": 50,
    "vad_aggressiveness": 3,
    "performance_targets": {
        "latency": 2.0,  # seconds
        "accuracy": 0.95,
        "cost_reduction": 0.30  # through VAD
    }
}
```

### API Rate Limiting
- Whisper API: 50 requests/minute (configurable)
- Automatic request queuing and retry logic
- Cost optimization through VAD filtering
- Performance monitoring via MonitoringCoordinator

## Project Setup

### Initial Setup
1. Clone repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure audio devices:
   - Enable WASAPI Exclusive Mode
   - Set system sample rate to 16kHz
   - Configure VB-Cable routing

### Environment Configuration
1. Set up MMCSS priority:
   - Audio service priority elevated
   - Thread priority configured for real-time audio
2. Configure power plan:
   - Set to High Performance
   - CPU minimum state > 50%
   - Disable USB selective suspend

## Testing

### Running Tests
```bash
# Run unit tests only (default)
python tests/run_tests.py

# Run all tests including 24-hour stability tests
python tests/run_tests.py --stability

# Run WASAPI-specific stability tests
python tests/run_tests.py --wasapi --duration 0.083  # 5 minutes

# Run specific test pattern
python tests/run_tests.py --pattern "test_audio*.py"

# Run specific test by name
python tests/run_tests.py --test-filter "recovery_mechanism"
```

### Test Types

#### Unit Tests (test_core.py)
- Component-level testing
- Mock hardware access
- Quick validation of functionality
- Automatic cleanup of resources

#### WASAPI Tests (test_wasapi_stability.py)
- WASAPI-specific stability testing
- Session monitoring validation
- Device change detection
- Recovery mechanism verification
- Known Issues:
  * Session monitoring requires stream activity proxy
  * High channel correlation expected for loopback
  * Recovery mechanism may need manual intervention
- Test Requirements:
  * Active audio playback (e.g., browser audio)
  * WASAPI loopback device available
  * System audio properly configured

#### Stability Tests (test_stability.py)
- 24-hour continuous operation testing
- Performance monitoring:
  * CPU usage (warning at >80%)
  * Memory usage (warning at >100MB)
  * Storage write latency (warning at >500ms)
- System health checks:
  * Audio stream stability
  * Memory leak detection
  * Error recovery effectiveness
- Detailed logging:
  * Performance metrics
  * Error counts by component
  * System recovery events
  * Test results saved to test_stability_{timestamp}/stability_test.log

### Test Environment Requirements
- Unique test directories for concurrent tests
- Mock audio hardware access in unit tests
- Real hardware required for stability tests
- Proper cleanup of resources and logs

### Common Test Issues
- File locking with logs: Fixed with proper handler cleanup
- WASAPI initialization: Use mock for hardware tests
- Audio processing: Verify normalization calculations
- Session monitoring: Use stream activity as proxy
- Recovery mechanism: May require multiple attempts
- Channel correlation: Adjust thresholds for loopback

## Troubleshooting

### Known Issues and Solutions
1. **WASAPI Stream Issues**
   - Verify WASAPI Exclusive Mode flag compatibility
   - Check pyaudiowpatch initialization
   - Use fallback modes when needed

2. **Audio Processing**
   - Verify audioop-lts import
   - Check normalization calculations
   - Monitor memory usage

3. **Test Framework**
   - Use unique directories for concurrent tests
   - Properly close log handlers
   - Mock hardware access

### Performance Monitoring
- CPU usage tracking
- Memory leak detection
- Audio stream health checks
- Storage I/O monitoring

### Debug Tools
- Audio analysis software (e.g., Audacity)
- Network monitoring tools
- Performance profiling tools
- Log analysis utilities

## Phase Completion Requirements

### 1. Testing Requirements
- **Comprehensive Test Suite**
  * All new components have unit tests
  * Integration tests for component interactions
  * End-to-end tests for new features
  * Performance benchmarks updated
  * 24-hour stability test passed

- **Test Coverage**
  * Minimum 90% code coverage
  * All edge cases tested
  * Error conditions verified
  * Recovery mechanisms validated

- **Test Documentation**
  * Test results documented
  * Performance metrics recorded
  * Known issues documented
  * Test environment details captured

### 2. Code Audit Requirements
- **Static Analysis**
  * Run linter on all new/modified code
  * Type hint verification
  * Complexity metrics within limits
  * No new warnings introduced

- **Code Review**
  * All new code reviewed
  * Best practices verified
  * Standards compliance checked
  * Security implications assessed

- **Architecture Review**
  * Component relationships verified
  * Interface contracts checked
  * State management validated
  * Resource handling confirmed

### 3. Documentation Requirements
- **Code Documentation**
  * All new code documented
  * Public APIs documented
  * Examples provided
  * Docstrings updated

- **Technical Documentation**
  * Architecture diagrams updated
  * Component interactions documented
  * Configuration details updated
  * Performance characteristics documented

- **User Documentation**
  * Feature documentation updated
  * Configuration guides updated
  * Troubleshooting guides updated
  * Examples and tutorials added

### 4. Phase Completion Checklist
1. **Testing Phase**
   - [ ] All tests passing
   - [ ] Coverage requirements met
   - [ ] Performance benchmarks passed
   - [ ] Test documentation updated

2. **Code Quality**
   - [ ] Static analysis clean
   - [ ] Code review completed
   - [ ] Architecture review passed
   - [ ] Best practices verified

3. **Documentation**
   - [ ] Code documentation complete
   - [ ] Technical docs updated
   - [ ] User docs updated
   - [ ] Examples provided

4. **Project Management**
   - [ ] Version numbers updated
   - [ ] Changelog updated
   - [ ] Release notes prepared
   - [ ] Migration guide if needed

5. **Final Verification**
   - [ ] 24-hour stability test
   - [ ] All issues documented
   - [ ] No blocking bugs
   - [ ] Phase goals met

## Known Issues and Tracking

### High Priority Issues
1. **Storage Performance (In Progress)**
   - Write latency optimization implemented (see Storage_Performance_Bug.md)
   - Buffer management improvements completed
   - Emergency backup protocol verified
   - Impact: 🟢 Minor - System stability improved

2. **Alert System Integration (Completed)**
   - ✓ Core alert system implemented with real-time monitoring
   - ✓ Resource thresholds configurable via AlertConfig
   - ✓ Integration with MonitoringCoordinator complete
   - ✓ Qt signals for UI notifications implemented
   - Monitors:
     * CPU usage (configurable threshold)
     * Memory usage (configurable threshold)
     * Storage latency (configurable threshold)
     * Buffer usage (configurable threshold)
   - Impact: System monitoring and reliability enhanced

3. **Configuration Management**
   - Central configuration system implemented
   - Component-specific configs consolidated
   - ✓ Backup policies implemented
   - Impact: System maintenance and reliability

### Medium Priority Issues
1. ✓ **Directory Organization** (Resolved)
   - ✓ Empty documentation directories removed
   - ✓ Redundant change management directories removed
   - ✓ Backup locations consolidated
   - ✓ Test output directories organized
   - ✓ Impact: Project maintenance and clarity improved

2. ✓ **Testing Infrastructure** (Resolved)
   - ✓ Test outputs consolidated under tests/results/
   - ✓ Test log retention policy implemented
   - ✓ Analysis dashboard developed
   - ✓ Impact: Test maintenance and analysis improved

3. ✓ **Logging System** (Resolved)
   - ✓ Logging hierarchies standardized
   - ✓ Log directories consolidated
   - ✓ Log locations centralized
   - ✓ Impact: Improved log analysis and maintenance

### Resolved Issues (v0.4.1)
1. **Thread Safety**
   - Added thread-safe StateMachine
   - Implemented standardized error handling
   - Added proper cleanup coordination

2. **Error Handling**
   - Standardized error reporting
   - Added state machine integration
   - Implemented proper error propagation

3. **Resource Management**
   - Added thread-safe operations
   - Implemented proper state tracking
   - Added coordinated cleanup

### Issue Tracking Process
1. **New Issues**
   - Document in this section
   - Assign priority level
   - Link to relevant documentation
   - Track implementation status

2. **Resolution Process**
   - Move to resolved section after fix
   - Document solution approach
   - Update affected documentation
   - Verify in next phase review

3. **Version Tracking**
   - Link issues to version numbers
   - Document in CHANGELOG.md
   - Update architecture docs
   - Review in phase completion

## Notes
- All version numbers specified are minimum requirements
- Some components may require administrative privileges
- Regular updates to all components recommended
- Backup solutions should be considered for production deployments
- Phase completion requirements are mandatory
- No exceptions to testing requirements
- Documentation must be updated before phase completion
- All issues must be tracked and resolved
