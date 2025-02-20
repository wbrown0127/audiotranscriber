"""
COMPONENT_NOTES:
{
    "name": "WindowsManager",
    "type": "Core Component",
    "description": "Windows-specific manager that handles version detection, API compatibility, MMCSS configuration, and fallback mechanisms",
    "relationships": {
        "diagram": "```mermaid
            graph TD
                WM[WindowsManager] --> WV[WindowsVersion]
                WM --> AV[APIVersion]
                WM --> MC[MMCSSConfig]
                WM --> FB[FallbackSystem]
                WM --> RL[RecoveryLogger]
                WV --> VD[VersionDetector]
                AV --> AC[APICompatibility]
                MC --> MS[MMCSSService]
                MC --> SP[SchedulingParams]
                FB --> AF[AudioFallback]
                FB --> UF[UIFallback]
                FB --> SF[SchedulerFallback]
                RL --> ES[ErrorStats]
        ```",
        "dependencies": {
            "WindowsVersion": "Version detection",
            "APIVersion": "API compatibility",
            "MMCSSConfig": "MMCSS management",
            "FallbackSystem": "Fallback handling",
            "RecoveryLogger": "Error logging",
            "VersionDetector": "OS detection",
            "APICompatibility": "API routing",
            "MMCSSService": "Service management",
            "SchedulingParams": "Task scheduling",
            "AudioFallback": "Audio alternatives",
            "UIFallback": "UI alternatives",
            "SchedulerFallback": "Task alternatives",
            "ErrorStats": "Error tracking"
        }
    },
    "notes": [
        "Detects Windows version",
        "Manages API compatibility",
        "Configures MMCSS service",
        "Provides fallback mechanisms",
        "Tracks system statistics",
        "Handles API errors"
    ],
    "usage": {
        "examples": [
            "manager = WindowsManager(base_path)",
            "manager.setup_mmcss()",
            "result = manager.safe_api_call('audio', 'CreateAudioGraph')",
            "stats = manager.get_system_info()"
        ]
    },
    "requirements": {
        "python_version": "3.13.1+",
        "dependencies": [
            "winreg",
            "win32api",
            "win32service",
            "pyaudiowpatch"
        ],
        "system": {
            "os": "Windows 10/11",
            "permissions": "Admin for MMCSS"
        }
    },
    "performance": {
        "execution_time": "Minimal overhead",
        "resource_usage": [
            "Light registry access",
            "Efficient API routing",
            "Minimal service impact",
            "Smart fallback selection"
        ]
    }
}
"""

import winreg
import ctypes
import os
from typing import Optional, Dict, Tuple, Any
from enum import Enum
import platform
import win32api
import win32security
import win32serviceutil
import win32service
import win32process
import pywintypes

class WindowsVersion(Enum):
    WINDOWS_10 = "Windows 10"
    WINDOWS_11 = "Windows 11"
    UNKNOWN = "Unknown"
    
class APIVersion(Enum):
    V1 = "v1"  # Windows 10 original
    V2 = "v2"  # Windows 10 updated
    V3 = "v3"  # Windows 11
    
from audio_transcriber.recovery_logger import RecoveryLogger

class WindowsManager:
    def __init__(self, base_path: str = "logs"):
        self.version = self._detect_real_version()
        self.api_version = self._get_api_version()
        self.fallback_enabled = False
        self.service_cache: Dict[str, Any] = {}
        # Use base_path directly since it already includes the logs directory
        self.recovery_logger = RecoveryLogger(base_path)
        self.error_count = 0
        self.fallback_count = 0
        self.mmcss_config = {}
        
    def _detect_real_version(self) -> WindowsVersion:
        """Detect actual Windows version using multiple methods."""
        try:
            # Method 1: Registry Check
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                build = int(winreg.QueryValueEx(key, "CurrentBuild")[0])
                if build >= 22000:  # Windows 11 minimum build
                    return WindowsVersion.WINDOWS_11
                    
            # Method 2: API Check
            version_info = win32api.GetVersionEx()
            if version_info.dwMajorVersion > 10 or \
               (version_info.dwMajorVersion == 10 and version_info.dwBuildNumber >= 22000):
                return WindowsVersion.WINDOWS_11
                
            return WindowsVersion.WINDOWS_10
            
        except Exception as e:
            print(f"Version detection error: {e}")
            return WindowsVersion.UNKNOWN
            
    def _get_api_version(self) -> APIVersion:
        """Determine appropriate API version."""
        if self.version == WindowsVersion.WINDOWS_11:
            return APIVersion.V3
        elif self.version == WindowsVersion.WINDOWS_10:
            # Check for updated Windows 10 features
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                  r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                    build = int(winreg.QueryValueEx(key, "CurrentBuild")[0])
                    return APIVersion.V2 if build >= 19041 else APIVersion.V1
            except:
                return APIVersion.V1
        return APIVersion.V1
        
    def verify_service_access(self, service_name: str) -> bool:
        """Verify access to Windows service."""
        try:
            status = win32serviceutil.QueryServiceStatus(service_name)
            return status[1] == win32service.SERVICE_RUNNING
        except pywintypes.error as e:
            print(f"Service access error: {e}")
            return False
            
    def get_api_path(self, feature: str) -> str:
        """Get appropriate API path based on version."""
        api_paths = {
            APIVersion.V1: {
                "audio": "Windows.Media.Audio.AudioGraph",
                "ui": "Windows.UI.Xaml",
                "scheduler": "Windows.ApplicationModel.Background"
            },
            APIVersion.V2: {
                "audio": "Windows.Media.Audio.AudioGraph2",
                "ui": "Windows.UI.Xaml.Controls",
                "scheduler": "Windows.ApplicationModel.Background.Extended"
            },
            APIVersion.V3: {
                "audio": "Windows.Media.Audio.AudioGraph3",
                "ui": "Microsoft.UI.Xaml",
                "scheduler": "Windows.ApplicationModel.Background.Advanced"
            }
        }
        return api_paths.get(self.api_version, {}).get(feature, 
               api_paths[APIVersion.V1][feature])  # Fallback to V1
               
    def setup_mmcss(self) -> bool:
        """Setup Multimedia Class Scheduler Service."""
        try:
            if not self.verify_service_access("MMCSS"):
                raise Exception("MMCSS not accessible")
                
            if self.version == WindowsVersion.WINDOWS_11:
                return self._setup_mmcss_win11()
            return self._setup_mmcss_win10()
            
        except Exception as e:
            print(f"MMCSS setup error: {e}")
            return self._setup_mmcss_fallback()
            
    def _setup_mmcss_win11(self) -> bool:
        """Windows 11 specific MMCSS setup."""
        try:
            # Set task priority
            task_name = "Audio"
            priority_class = win32process.HIGH_PRIORITY_CLASS
            
            # Configure scheduling
            scheduling_params = {
                "TaskName": task_name,
                "Priority": priority_class,
                "Latency": 1,  # 1ms target latency
                "CPUCores": "0-3"  # First 4 cores
            }
            
            return self._configure_mmcss(scheduling_params)
            
        except Exception as e:
            print(f"Win11 MMCSS setup failed: {e}")
            return False
            
    def _setup_mmcss_win10(self) -> bool:
        """Windows 10 specific MMCSS setup."""
        try:
            task_name = "Audio"
            priority_class = win32process.ABOVE_NORMAL_PRIORITY_CLASS
            
            scheduling_params = {
                "TaskName": task_name,
                "Priority": priority_class,
                "Latency": 2,  # 2ms target latency
                "CPUCores": "0-2"  # First 3 cores
            }
            
            return self._configure_mmcss(scheduling_params)
            
        except Exception as e:
            print(f"Win10 MMCSS setup failed: {e}")
            return False
            
    def _setup_mmcss_fallback(self) -> bool:
        """Fallback MMCSS configuration."""
        try:
            # Basic priority boost
            task_name = "Audio"
            priority_class = win32process.ABOVE_NORMAL_PRIORITY_CLASS
            
            scheduling_params = {
                "TaskName": task_name,
                "Priority": priority_class,
                "Latency": 10,  # 10ms target latency
                "CPUCores": "0-1"  # First 2 cores
            }
            
            return self._configure_mmcss(scheduling_params)
            
        except Exception as e:
            print(f"Fallback MMCSS setup failed: {e}")
            return False
            
    def _configure_mmcss(self, params: Dict[str, Any]) -> bool:
        """Configure MMCSS with given parameters."""
        try:
            # Set process priority
            current_process = win32api.GetCurrentProcess()
            win32process.SetPriorityClass(current_process, params["Priority"])
            
            # Configure MMCSS task
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Audio",
                              0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "Latency", 0, winreg.REG_DWORD, params["Latency"])
                winreg.SetValueEx(key, "Priority", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "Clock Rate", 0, winreg.REG_DWORD, 10000)
                winreg.SetValueEx(key, "SFIO Priority", 0, winreg.REG_SZ, "Normal")
                
            self.mmcss_config = params
            return True
            
        except Exception as e:
            print(f"MMCSS configuration failed: {e}")
            return False
            
    def safe_api_call(self, feature: str, method: str, *args, **kwargs) -> Any:
        """Make API calls with version checking and fallback."""
        try:
            api_path = self.get_api_path(feature)
            if self.fallback_enabled:
                self.fallback_count += 1
                return self._fallback_api_call(feature, method, *args, **kwargs)
                
            module = __import__(api_path, fromlist=[method])
            func = getattr(module, method)
            return func(*args, **kwargs)
            
        except ImportError:
            print(f"API not available: {api_path}")
            self.fallback_enabled = True
            self.fallback_count += 1
            return self._fallback_api_call(feature, method, *args, **kwargs)
            
        except Exception as e:
            print(f"API call error: {e}")
            self.error_count += 1
            self.last_error = str(e)
            return None
            
    def _fallback_api_call(self, feature: str, method: str, *args, **kwargs) -> Any:
        """Implement fallback behavior for API calls."""
        fallbacks = {
            "audio": self._audio_fallbacks,
            "ui": self._ui_fallbacks,
            "scheduler": self._scheduler_fallbacks
        }
        
        handler = fallbacks.get(feature)
        if handler:
            return handler(method, *args, **kwargs)
        return None
        
    def _audio_fallbacks(self, method: str, *args, **kwargs) -> Any:
        """Audio API fallbacks."""
        if method == "CreateAudioGraph":
            return self._create_basic_audio_graph(*args, **kwargs)
        return None
        
    def _ui_fallbacks(self, method: str, *args, **kwargs) -> Any:
        """UI API fallbacks."""
        if method == "CreateWindow":
            return self._create_basic_window(*args, **kwargs)
        return None
        
    def _scheduler_fallbacks(self, method: str, *args, **kwargs) -> Any:
        """Scheduler API fallbacks."""
        if method == "RegisterTask":
            return self._register_basic_task(*args, **kwargs)
        return None
        
    def _create_basic_audio_graph(self, *args, **kwargs) -> Any:
        """Basic audio graph implementation."""
        try:
            import pyaudiowpatch as pyaudio
            pa = pyaudio.PyAudio()
            return pa.open(
                format=pyaudio.paFloat32,
                channels=kwargs.get('channels', 2),
                rate=kwargs.get('sample_rate', 48000),
                input=True,
                output=False
            )
        except Exception as e:
            print(f"Basic audio graph creation failed: {e}")
            return None
            
    def _create_basic_window(self, *args, **kwargs) -> Any:
        """Basic window implementation."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.title(kwargs.get('title', 'Audio Application'))
            root.geometry(f"{kwargs.get('width', 800)}x{kwargs.get('height', 600)}")
            return root
        except Exception as e:
            print(f"Basic window creation failed: {e}")
            return None
            
    def _register_basic_task(self, *args, **kwargs) -> Any:
        """Basic task registration."""
        try:
            import win32com.client
            scheduler = win32com.client.Dispatch('Schedule.Service')
            scheduler.Connect()
            
            root_folder = scheduler.GetFolder('\\')
            task_def = scheduler.NewTask(0)
            
            # Create basic trigger
            trigger = task_def.Triggers.Create(1)  # TASK_TRIGGER_TIME
            trigger.StartBoundary = kwargs.get('start_time', '2000-01-01T12:00:00')
            trigger.Enabled = True
            
            return root_folder.RegisterTaskDefinition(
                kwargs.get('name', 'AudioTask'),
                task_def,
                6,  # TASK_CREATE_OR_UPDATE
                None,  # No user
                None,  # No password
                0  # TASK_LOGON_NONE
            )
            
        except Exception as e:
            print(f"Basic task registration failed: {e}")
            return None
            
    def get_system_info(self) -> dict:
        """Get detailed system information."""
        return {
            'version': self.version.value,
            'api_version': self.api_version.value,
            'fallback_enabled': self.fallback_enabled,
            'mmcss_status': self.verify_service_access("MMCSS"),
            'build_number': self._get_build_number()
        }
        
    def _get_build_number(self) -> Optional[int]:
        """Get Windows build number."""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                return int(winreg.QueryValueEx(key, "CurrentBuild")[0])
        except Exception:
            return None

    def get_fallback_stats(self) -> dict:
        """Get statistics about fallback API usage."""
        return {
            'fallback_enabled': self.fallback_enabled,
            'fallback_count': self.fallback_count,
            'active_fallbacks': {
                'audio': self._audio_fallbacks is not None,
                'ui': self._ui_fallbacks is not None,
                'scheduler': self._scheduler_fallbacks is not None
            }
        }

    def get_error_stats(self) -> dict:
        """Get API error statistics."""
        return {
            'total_errors': self.error_count,
            'error_rate': self.error_count / max(1, self.error_count + self.fallback_count),
            'last_error': getattr(self, 'last_error', None)
        }

    def get_mmcss_status(self) -> dict:
        """Get MMCSS configuration status."""
        try:
            status = win32serviceutil.QueryServiceStatus("MMCSS")
            return {
                'service_running': status[1] == win32service.SERVICE_RUNNING,
                'config': self.mmcss_config,
                'priority_enabled': win32process.GetPriorityClass(win32api.GetCurrentProcess()) > win32process.NORMAL_PRIORITY_CLASS
            }
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            return {
                'service_running': False,
                'config': {},
                'error': str(e)
            }
