"""Fail-closed interface for a future isolated evaluation executor.

A Python subprocess and audit hooks cannot isolate hostile code from the worker
filesystem, credentials, native libraries, or child processes. Execution remains
unavailable until an independently isolated executor is implemented and verified.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SandboxConfig:
    cpu_seconds: int = 3
    mem_bytes: int = 128 * 1024 * 1024
    max_file_bytes: int = 64 * 1024
    timeout_seconds: float = 5.0
    max_output_bytes: int = 65536


@dataclass(frozen=True)
class SandboxResult:
    status: str
    output: Any | None
    stdout: str
    stderr: str
    duration_ms: float
    error: str | None


def execute_sandboxed(code: str, input_payload: Any, config: SandboxConfig | None = None) -> SandboxResult:
    """Reject execution without starting a process or evaluating submitted code."""
    return SandboxResult(
        status="BLOCKED",
        output=None,
        stdout="",
        stderr="",
        duration_ms=0.0,
        error="Isolated evaluation executor unavailable; submitted code was not executed.",
    )
