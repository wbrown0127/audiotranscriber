"""Component state definitions for the audio transcriber system."""

import enum

class ComponentState(enum.Enum):
    """States for component lifecycle."""
    UNINITIALIZED = "uninitialized"
    IDLE = "idle"
    INITIALIZING = "initializing"
    INITIATING = "initiating"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPING_CAPTURE = "stopping_capture"
    STOPPED = "stopped"
    ERROR = "error"
