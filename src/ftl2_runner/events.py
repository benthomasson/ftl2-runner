"""Event translation from FTL2 to ansible-runner format."""

import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable


class EventTranslator:
    """Translate FTL2 events to ansible-runner format.

    FTL2 emits events like:
        {"event": "module_start", "module": "ping", "host": "localhost", ...}
        {"event": "module_complete", "module": "ping", "host": "localhost", "success": True, ...}

    We translate to ansible-runner format:
        {"event": "runner_on_start", "uuid": "...", "counter": 1, ...}
        {"event": "runner_on_ok", "uuid": "...", "counter": 2, ...}
    """

    def __init__(self, ident: str, on_event: Callable[[dict], None] | None = None):
        """Initialize translator.

        Args:
            ident: Runner identifier (job ID)
            on_event: Callback for translated events
        """
        self.ident = ident
        self.on_event = on_event
        self._counter = 0
        self._line = 0
        self._playbook_uuid: str | None = None
        self._play_uuid: str | None = None
        self._task_uuid: str | None = None

    def _next_counter(self) -> int:
        """Get next event counter."""
        self._counter += 1
        return self._counter

    def _add_stdout_fields(self, event: dict[str, Any]) -> None:
        """Add stdout, start_line, end_line to an event."""
        stdout = self._format_stdout(event)
        n_lines = stdout.count("\n") + (1 if stdout else 0)
        event["stdout"] = stdout
        event["start_line"] = self._line
        event["end_line"] = self._line + n_lines
        self._line += n_lines

    def _format_stdout(self, event: dict[str, Any]) -> str:
        """Format stdout text for an event, mimicking Ansible output."""
        event_type = event.get("event", "")
        event_data = event.get("event_data", {})

        if event_type == "runner_on_ok":
            host = event_data.get("host", "localhost")
            res = event_data.get("res", {})
            changed = event_data.get("changed", False)
            prefix = "changed" if changed else "ok"
            return f"{prefix}: [{host}] => {json.dumps(res, indent=4, default=str)}"

        elif event_type == "runner_on_failed":
            host = event_data.get("host", "localhost")
            res = event_data.get("res", {})
            return f"fatal: [{host}]: FAILED! => {json.dumps(res, indent=4, default=str)}"

        elif event_type == "playbook_on_play_start":
            play_name = event_data.get("play", {}).get("name", "")
            header = f"\nPLAY [{play_name}] "
            return header + "*" * max(0, 76 - len(header))

        elif event_type == "playbook_on_task_start":
            task_name = event_data.get("task", {}).get("name", "")
            header = f"\nTASK [{task_name}] "
            return header + "*" * max(0, 76 - len(header))

        return ""

    def _format_stats_stdout(self, per_host_stats: dict[str, dict[str, int]]) -> str:
        """Format PLAY RECAP stdout for stats event."""
        lines = ["\nPLAY RECAP " + "*" * 65]
        for host, counts in per_host_stats.items():
            ok = counts.get("ok", 0)
            changed = counts.get("changed", 0)
            unreachable = counts.get("unreachable", 0)
            failed = counts.get("failed", 0)
            skipped = counts.get("skipped", 0)
            line = (
                f"{host:<26}: ok={ok:<4} changed={changed:<4} "
                f"unreachable={unreachable:<4} failed={failed:<4} "
                f"skipped={skipped:<4}"
            )
            lines.append(line)
        return "\n".join(lines)

    def translate(self, ftl2_event: dict[str, Any]) -> dict[str, Any]:
        """Translate FTL2 event to ansible-runner format.

        Args:
            ftl2_event: FTL2 event dict

        Returns:
            ansible-runner format event dict
        """
        event_type = ftl2_event.get("event", "")
        event_uuid = str(uuid.uuid4())
        counter = self._next_counter()
        timestamp = datetime.now(timezone.utc).isoformat()

        # Base event structure
        ar_event: dict[str, Any] = {
            "uuid": event_uuid,
            "counter": counter,
            "created": timestamp,
            "runner_ident": self.ident,
        }

        if event_type == "module_start":
            ar_event["event"] = "runner_on_start"
            ar_event["event_data"] = {
                "host": ftl2_event.get("host", "localhost"),
                "task": ftl2_event.get("module", "unknown"),
                "task_action": ftl2_event.get("module", "unknown"),
            }

        elif event_type == "module_complete":
            success = ftl2_event.get("success", False)
            ar_event["event"] = "runner_on_ok" if success else "runner_on_failed"
            ar_event["event_data"] = {
                "host": ftl2_event.get("host", "localhost"),
                "task": ftl2_event.get("module", "unknown"),
                "task_action": ftl2_event.get("module", "unknown"),
                # FTL2 uses 'output', fallback to 'result' for backward compatibility
                "res": ftl2_event.get("output") or ftl2_event.get("result", {}),
                "changed": ftl2_event.get("changed", False),
            }
            if "duration" in ftl2_event:
                ar_event["event_data"]["duration"] = ftl2_event["duration"]

        else:
            # Pass through unknown events with a generic mapping
            ar_event["event"] = f"runner_{event_type}"
            ar_event["event_data"] = {
                k: v for k, v in ftl2_event.items() if k != "event"
            }

        # Add parent_uuid for runner events
        if self._task_uuid and ar_event.get("event", "").startswith("runner_on_"):
            ar_event["parent_uuid"] = self._task_uuid

        # Add stdout and line tracking
        self._add_stdout_fields(ar_event)

        return ar_event

    def __call__(self, ftl2_event: dict[str, Any]) -> None:
        """Handle FTL2 event callback.

        Translates and forwards to on_event callback.
        """
        ar_event = self.translate(ftl2_event)
        if self.on_event:
            self.on_event(ar_event)

    def create_playbook_start_event(self) -> dict[str, Any]:
        """Create playbook_on_start hierarchy event."""
        playbook_uuid = str(uuid.uuid4())
        self._playbook_uuid = playbook_uuid
        event: dict[str, Any] = {
            "uuid": playbook_uuid,
            "counter": self._next_counter(),
            "created": datetime.now(timezone.utc).isoformat(),
            "runner_ident": self.ident,
            "event": "playbook_on_start",
            "event_data": {
                "playbook": "ftl2_script",
                "uuid": playbook_uuid,
            },
        }
        self._add_stdout_fields(event)
        return event

    def create_play_start_event(self, play_name: str = "FTL2 Script") -> dict[str, Any]:
        """Create playbook_on_play_start hierarchy event."""
        play_uuid = str(uuid.uuid4())
        self._play_uuid = play_uuid
        event: dict[str, Any] = {
            "uuid": play_uuid,
            "counter": self._next_counter(),
            "created": datetime.now(timezone.utc).isoformat(),
            "runner_ident": self.ident,
            "event": "playbook_on_play_start",
            "event_data": {
                "play": {
                    "name": play_name,
                    "id": play_uuid,
                },
            },
            "parent_uuid": self._playbook_uuid,
        }
        self._add_stdout_fields(event)
        return event

    def create_task_start_event(self, task_name: str, task_action: str) -> dict[str, Any]:
        """Create playbook_on_task_start hierarchy event."""
        task_uuid = str(uuid.uuid4())
        self._task_uuid = task_uuid
        event: dict[str, Any] = {
            "uuid": task_uuid,
            "counter": self._next_counter(),
            "created": datetime.now(timezone.utc).isoformat(),
            "runner_ident": self.ident,
            "event": "playbook_on_task_start",
            "event_data": {
                "task": {
                    "name": task_name,
                    "id": task_uuid,
                },
                "task_action": task_action,
            },
            "parent_uuid": self._play_uuid,
        }
        self._add_stdout_fields(event)
        return event

    def create_stats_event(self, per_host_stats: dict[str, dict[str, int]]) -> dict[str, Any]:
        """Create playbook_on_stats event with AWX-compatible format.

        Transposes per-host stats to per-status format expected by AWX.

        Args:
            per_host_stats: Dict like {"host1": {"ok": 5, "changed": 2, "failed": 0}}

        Returns:
            Stats event dict with transposed format
        """
        # Transpose from per-host to per-status format
        transposed: dict[str, dict[str, int]] = {
            "ok": {},
            "changed": {},
            "failures": {},
            "dark": {},
            "skipped": {},
        }
        for host, counts in per_host_stats.items():
            for host_key, awx_key in [
                ("ok", "ok"),
                ("changed", "changed"),
                ("failed", "failures"),
                ("skipped", "skipped"),
            ]:
                count = counts.get(host_key, 0)
                if count:
                    transposed[awx_key][host] = count

        # Format stdout from original per-host stats
        stdout = self._format_stats_stdout(per_host_stats)
        n_lines = stdout.count("\n") + (1 if stdout else 0)

        event: dict[str, Any] = {
            "uuid": str(uuid.uuid4()),
            "counter": self._next_counter(),
            "created": datetime.now(timezone.utc).isoformat(),
            "runner_ident": self.ident,
            "event": "playbook_on_stats",
            "event_data": transposed,
            "parent_uuid": self._playbook_uuid,
            "stdout": stdout,
            "start_line": self._line,
            "end_line": self._line + n_lines,
        }
        self._line += n_lines
        return event


def create_status_event(
    status: str,
    ident: str,
    counter: int,
    command: list[str] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a status event.

    Args:
        status: Status string (starting, running, successful, failed, etc.)
        ident: Runner identifier
        counter: Event counter
        command: Command being run (for starting status)
        cwd: Working directory (for starting status)
        env: Environment variables (for starting status)

    Returns:
        Status event dict
    """
    event: dict[str, Any] = {
        "uuid": str(uuid.uuid4()),
        "counter": counter,
        "created": datetime.now(timezone.utc).isoformat(),
        "runner_ident": ident,
        "event": "status",
        "event_data": {
            "status": status,
        },
    }

    if status == "starting" and command:
        event["event_data"]["command"] = command
        if cwd:
            event["event_data"]["cwd"] = cwd
        if env:
            event["event_data"]["env"] = env

    return event


def create_playbook_stats_event(
    ident: str,
    counter: int,
    stats: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Create playbook stats event (end of run).

    Args:
        ident: Runner identifier
        counter: Event counter
        stats: Per-host stats dict like {"host1": {"ok": 5, "changed": 2, "failed": 0}}

    Returns:
        Stats event dict
    """
    return {
        "uuid": str(uuid.uuid4()),
        "counter": counter,
        "created": datetime.now(timezone.utc).isoformat(),
        "runner_ident": ident,
        "event": "playbook_on_stats",
        "event_data": {
            "stats": stats,
        },
    }


def encode_event_ansi(event_data: dict[str, Any], max_width: int = 78) -> str:
    """Encode event data as ANSI escape sequence for OutputEventFilter extraction.

    Matches the format from ansible-runner's awx_display callback plugin.
    The cursor-backward codes make the encoded data invisible on terminals.

    Args:
        event_data: Event dict to encode (event, uuid, created, event_data, etc.)
        max_width: Max width of base64 chunks (default 78, matches awx_display)

    Returns:
        ANSI-encoded string to write to stdout
    """
    b64data = base64.b64encode(
        json.dumps(event_data, default=str).encode("utf-8")
    ).decode()
    parts = ["\x1b[K"]
    for offset in range(0, len(b64data), max_width):
        chunk = b64data[offset:offset + max_width]
        parts.append(f"{chunk}\x1b[{len(chunk)}D")
    parts.append("\x1b[K")
    return "".join(parts)


def event_to_json(event: dict[str, Any]) -> str:
    """Convert event to JSON string for streaming."""
    return json.dumps(event, ensure_ascii=False, default=str)
