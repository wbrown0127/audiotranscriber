# Audio Transcriber Prerequisites

## Hardware Requirements

### CPU & Memory
- [ ] Intel i5-8250U or better CPU
  - Required for AVX2 instruction support
  - Needed for WASAPI optimizations
- [ ] 4GB DDR4 RAM minimum
  - 2GB reserved for dedicated audio buffers
  - Remaining for system and application overhead

### Storage
- [ ] 100MB+ NVMe storage
  - MSIX package requirements
  - Temporary file processing
  - Log file storage

### Audio Interface
- [ ] VB-Cable Virtual Audio Device ($59 license required)
  - Essential for channel isolation
  - Required for 3CX integration
- [ ] Realtek or compatible sound card
  - Must support WASAPI exclusive mode
  - 16-bit/16kHz capability required

## Software Requirements

### Operating System
- [ ] Windows 10 22H2 or Windows 11
  - Compatible with both standard and N/KN editions
  - All latest Windows updates installed
- [ ] Multimedia Class Scheduler Service (MMCSS) enabled
- [ ] Windows Media Foundation support
- [ ] .NET Runtime 6.0 or newer

### Development Environment
- [ ] Python 3.10.x (specific version for PyAudio wheel compatibility)
- [ ] pip package manager (latest version)
- [ ] Microsoft Visual C++ Build Tools 2019 or newer
  - Required for compiling certain dependencies
  - Windows SDK 10.0.19041.0 or newer
- [ ] Git for version control
- [ ] WiX Toolset v3.11.2 or newer (for MSIX packaging)

### Python Packages

#### Core Dependencies
```
PySide6==6.5.3
openai>=1.3.6
numpy>=1.24.3
watchdog>=3.0.0
python-webrtcvad>=2.0.10
```

#### Windows-Specific Packages
```
PyAudio (custom wheel for cp310)
pywin32==306
WASAPI-Devices==0.5.0
comtypes==1.2.0
```

## Service Configurations

### OpenAI API Setup
- [ ] Active OpenAI account with billing enabled
- [ ] API key generated and accessible
- [ ] Usage limits configured (~$0.006/minute of audio)
- [ ] Billing alerts set up (recommended)

### Audio Configuration
- [ ] WASAPI Exclusive Mode enabled in Windows sound settings
- [ ] Sample rate set to 16000 Hz as system default
- [ ] VB-Cable configuration:
  - Left channel routed from 3CX
  - Right channel routed from microphone
  - Device properly recognized in Windows audio devices

### System Optimizations
- [ ] MMCSS Priority Settings
  - Audio service priority elevated
  - Thread priority configured for real-time audio
- [ ] Power Plan Configuration
  - Set to High Performance or Ultimate Performance
  - CPU minimum state > 50%
  - USB selective suspend disabled
  - Hard disk timeout increased

## Testing Environment

### Basic Testing Setup
- [ ] CRC validation tools installed
- [ ] Audio testing equipment:
  - Test microphone
  - Test speakers/headphones
  - Audio loopback capability

### Extended Testing Requirements
- [ ] Stress testing environment capable of 8+ hour sessions
- [ ] Multiple Windows versions for compatibility testing:
  - Windows 10 22H2
  - Windows 11
  - N/KN editions of both
- [ ] Network simulation tools for API testing

## Deployment Prerequisites

### Code Signing
- [ ] Valid code signing certificate
  - EV Certificate recommended for MSIX
  - Compatible with Microsoft Store requirements

### Distribution
- [ ] Windows Store developer account (if planning store distribution)
- [ ] Update infrastructure:
  - Web hosting for updates
  - CDN configuration (recommended)
  - Update manifest templates

## Network Requirements

### Connectivity
- [ ] Stable internet connection (5Mbps+ upload recommended)
- [ ] Firewall configurations:
  - OpenAI API endpoints whitelisted
  - Update server endpoints whitelisted
- [ ] Proxy configurations (if applicable)

### Security
- [ ] SSL certificates for update server
- [ ] API key encryption mechanism
- [ ] Secure storage for credentials

## Documentation
- [ ] Installation guide
- [ ] Configuration templates
- [ ] Troubleshooting guide
- [ ] API documentation
- [ ] User manual

## Optional Tools
- [ ] Audio analysis software (e.g., Audacity)
- [ ] Network monitoring tools
- [ ] Performance profiling tools
- [ ] Memory leak detection tools
- [ ] Log analysis tools

## Notes
- All version numbers specified are minimum requirements
- Some components may require administrative privileges to install/configure
- Regular updates to all components recommended
- Backup solutions should be considered for production deployments
