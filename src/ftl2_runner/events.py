"""Event translation from FTL2 to ansible-runner format."""

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

    def _next_counter(self) -> int:
        """Get next event counter."""
        self._counter += 1
        return self._counter

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

        return ar_event

    def __call__(self, ftl2_event: dict[str, Any]) -> None:
        """Handle FTL2 event callback.

        Translates and forwards to on_event callback.
        """
        ar_event = self.translate(ftl2_event)
        if self.on_event:
            self.on_event(ar_event)


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


def event_to_json(event: dict[str, Any]) -> str:
    """Convert event to JSON string for streaming."""
    return json.dumps(event, ensure_ascii=False, default=str)
