# Audio Transcriber Development Documentation

## Documentation Structure

### Architecture
- [System Architecture](architecture/architecture.md) - System design and component diagrams
- [Component Relationships](architecture/component_relationships.md) - Detailed component interactions

### Implementation
- [Core Stability](implementation/core_stability.md) - Thread safety and stability implementation
- [Transcription](implementation/transcription.md) - Transcription system implementation
- [Buffer Management](buffer_management.md) - Buffer management system
- [Performance Guide](performance.md) - Performance tuning and optimization
- [Structure Improvements](structure_improvements.md) - Structural improvements
- [Transcription Display](transcription_display.md) - Display system implementation
- [Troubleshooting](troubleshooting.md) - System troubleshooting guide

### Project Status
- [Project Status](status/PROJECT_STATUS.md) - Comprehensive project status and roadmap
- [Status Dashboard](status/STATUS_SUMMARY.md) - Key metrics and health indicators

### Change Tracking
- [File Structure](tracking/file_tracker.md) - Project file organization
- [Change History](tracking/CHANGELOG.md) - Version history and changes

## Development Standards

### Code Organization
- Use pathlib.Path for all paths
- Define paths in central configuration
- Use relative paths from project root
- Use absolute imports from project root
- Group imports: stdlib → third-party → local
- Avoid circular dependencies
- Resource Management:
  * MonitoringCoordinator owns ResourcePool
  * ResourcePool injected into dependent components
  * No direct resource sharing between components
  * Follow established initialization order

### Thread Safety
- Use ComponentCoordinator for lifecycle
- Use MonitoringCoordinator for metrics
- Follow lock ordering rules
- Use atomic state updates
- Follow cleanup protocol
- Use standardized monitoring

### File Operations
- Use async operations (aiofiles)
- Implement context managers
- Follow error handling standards
- Follow backup retention policies
- Use emergency backup for crashes

### Testing
- Store outputs in tests/results/
- Follow TEST_POLICY.md guidelines
- Run cleanup_test_outputs.py regularly
- Use analyze_results.py for trends
- Maintain test coverage standards

### Change Management
- Document changes in CHANGELOG.md
- Use templates from templates/
- Follow semantic versioning
- One change per commit
- Move resolved bugs to archive/

### Documentation
- Keep docs in appropriate directories
- Update file_tracker.md for changes
- Follow policy documents
- Maintain architecture diagrams
- Document performance impacts
