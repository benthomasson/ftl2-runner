"""Artifact directory management for ansible-runner compatibility."""

import json
import os
import stat
from pathlib import Path
from typing import Any


class ArtifactWriter:
    """Write artifacts in ansible-runner format.

    Creates and manages the artifact directory structure that AWX expects:
        artifacts/<ident>/
        ├── job_events/
        │   ├── 1-<uuid>.json
        │   └── 2-<uuid>.json
        ├── stdout
        ├── stderr
        ├── rc
        ├── status
        └── command
    """

    def __init__(self, artifact_dir: Path, ident: str):
        """Initialize artifact writer.

        Args:
            artifact_dir: Base artifact directory
            ident: Run identifier
        """
        self.artifact_dir = artifact_dir
        self.ident = ident
        self._event_counter = 0
        self._stdout_buffer: list[str] = []
        self._stderr_buffer: list[str] = []

    def setup(self) -> None:
        """Create the artifact directory structure."""
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.artifact_dir, stat.S_IRWXU)

        job_events_dir = self.artifact_dir / "job_events"
        job_events_dir.mkdir(exist_ok=True)
        os.chmod(job_events_dir, stat.S_IRWXU)

        # Create empty stdout and stderr files
        for filename in ("stdout", "stderr"):
            filepath = self.artifact_dir / filename
            filepath.touch()
            os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)

    def write_event(self, event: dict[str, Any]) -> None:
        """Write event to job_events directory.

        Args:
            event: Event dictionary with uuid, counter, etc.
        """
        counter = event.get("counter", self._next_counter())
        uuid = event.get("uuid", "unknown")

        filename = f"{counter}-{uuid}.json"
        event_path = self.artifact_dir / "job_events" / filename

        # Write atomically via temp file
        temp_path = event_path.with_suffix(".json.tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
            json.dump(event, f, ensure_ascii=False)
        temp_path.rename(event_path)

    def append_stdout(self, content: str) -> None:
        """Append content to stdout file.

        Args:
            content: Content to append
        """
        self._stdout_buffer.append(content)
        with open(self.artifact_dir / "stdout", "a", encoding="utf-8") as f:
            f.write(content)

    def append_stderr(self, content: str) -> None:
        """Append content to stderr file.

        Args:
            content: Content to append
        """
        self._stderr_buffer.append(content)
        with open(self.artifact_dir / "stderr", "a", encoding="utf-8") as f:
            f.write(content)

    def write_rc(self, rc: int) -> None:
        """Write return code file.

        Args:
            rc: Return code
        """
        rc_path = self.artifact_dir / "rc"
        rc_path.touch()
        os.chmod(rc_path, stat.S_IRUSR | stat.S_IWUSR)
        rc_path.write_text(str(rc))

    def write_status(self, status: str) -> None:
        """Write status file.

        Args:
            status: Status string
        """
        status_path = self.artifact_dir / "status"
        status_path.touch()
        os.chmod(status_path, stat.S_IRUSR | stat.S_IWUSR)
        status_path.write_text(status)

    def write_command(self, command: dict[str, Any]) -> None:
        """Write command file with execution details.

        Args:
            command: Dictionary with command, cwd, env
        """
        command_path = self.artifact_dir / "command"
        command_path.touch()
        os.chmod(command_path, stat.S_IRUSR | stat.S_IWUSR)
        with open(command_path, "w", encoding="utf-8") as f:
            json.dump(command, f, ensure_ascii=False)

    def _next_counter(self) -> int:
        """Get next event counter value."""
        self._event_counter += 1
        return self._event_counter

    @property
    def stdout_path(self) -> Path:
        """Path to stdout file."""
        return self.artifact_dir / "stdout"

    @property
    def stderr_path(self) -> Path:
        """Path to stderr file."""
        return self.artifact_dir / "stderr"
