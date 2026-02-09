"""Capacity information for --worker-info compatibility."""

import os
import uuid
from pathlib import Path

VERSION = "0.1.0"


def get_cpu_count() -> int:
    """Get the number of CPUs available."""
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def get_mem_in_bytes() -> int:
    """Get total memory in bytes."""
    try:
        # Try Linux /proc/meminfo first
        meminfo_path = Path("/proc/meminfo")
        if meminfo_path.exists():
            with open(meminfo_path) as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        # MemTotal is in kB
                        parts = line.split()
                        return int(parts[1]) * 1024

        # Try macOS sysctl
        import subprocess
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass

    # Default to 4GB if we can't determine
    return 4 * 1024 * 1024 * 1024


def get_runner_version() -> str:
    """Get the ftl2-runner version."""
    return VERSION


def get_uuid() -> str:
    """Get or generate a persistent UUID for this node."""
    # Try to read from a file first for persistence
    uuid_file = Path("/etc/ftl2-runner-uuid")

    try:
        if uuid_file.exists():
            return uuid_file.read_text().strip()
    except Exception:
        pass

    # Generate a new UUID
    return str(uuid.uuid4())


def get_worker_info() -> dict:
    """Get worker info dict for --worker-info response."""
    return {
        "mem_in_bytes": get_mem_in_bytes(),
        "cpu_count": get_cpu_count(),
        "runner_version": get_runner_version(),
        "uuid": get_uuid(),
    }
