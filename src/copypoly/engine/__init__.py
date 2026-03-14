"""Copy Trading Engine package.

Core components:
- signal_detector — Converts position changes into CopySignals
- executor        — Paper and Live order execution
"""

from copypoly.engine.executor import (
    CopyEngine,
    ExecutionResult,
    LiveExecutor,
    PaperExecutor,
)
from copypoly.engine.signal_detector import SignalDetector, evaluate_signal

__all__ = [
    "CopyEngine",
    "ExecutionResult",
    "LiveExecutor",
    "PaperExecutor",
    "SignalDetector",
    "evaluate_signal",
]
