"""ftl2-runner: ansible-runner compatibility layer for FTL2.

This package provides a drop-in replacement for ansible-runner's worker mode,
allowing AWX to use FTL2 for execution instead of standard Ansible.
"""

from ftl2_runner.capacity import get_worker_info
from ftl2_runner.events import EventTranslator
from ftl2_runner.runner_context import RunnerContext
from ftl2_runner.worker import run_worker

__version__ = "0.4.0"

__all__ = [
    "get_worker_info",
    "EventTranslator",
    "RunnerContext",
    "run_worker",
    "__version__",
]
