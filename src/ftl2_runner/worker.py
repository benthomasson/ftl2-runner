"""Worker implementation for ftl2-runner.

This handles the main execution flow:
1. Read streaming data from stdin
2. Unpack to private_data_dir
3. Load inventory and extravars
4. Execute baked-in FTL2 script
5. Stream events to stdout
6. Write artifacts
"""

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from ftl2_runner.events import (
    EventTranslator,
    create_playbook_stats_event,
    create_status_event,
)
from ftl2_runner.streaming import (
    read_input_stream,
    stream_dir,
    write_eof,
    write_event,
    write_status,
)
from ftl2_runner.artifacts import ArtifactWriter


# Default location for baked-in FTL2 script
DEFAULT_SCRIPT_PATH = "/opt/ftl2/main.py"


def load_extravars(private_data_dir: str) -> dict[str, Any]:
    """Load extravars from private_data_dir/env/extravars.

    Args:
        private_data_dir: Base directory

    Returns:
        Dict of extra variables, empty if file doesn't exist
    """
    extravars_path = Path(private_data_dir) / "env" / "extravars"

    if not extravars_path.exists():
        return {}

    try:
        content = extravars_path.read_text()
        return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return {}


def get_inventory_path(private_data_dir: str) -> str | None:
    """Get path to inventory directory.

    Args:
        private_data_dir: Base directory

    Returns:
        Path to inventory directory, or None if not found
    """
    inventory_dir = Path(private_data_dir) / "inventory"

    if inventory_dir.exists() and inventory_dir.is_dir():
        return str(inventory_dir)

    return None


def get_ident(private_data_dir: str, kwargs: dict[str, Any]) -> str:
    """Get runner identifier from kwargs or generate one.

    Args:
        private_data_dir: Base directory
        kwargs: Job kwargs

    Returns:
        Identifier string
    """
    if "ident" in kwargs:
        return str(kwargs["ident"])

    # Try to extract from private_data_dir path
    path = Path(private_data_dir)
    if path.name.startswith("awx_"):
        return path.name.replace("awx_", "")

    return "1"


def load_baked_script(script_path: str) -> Callable | None:
    """Load the baked-in FTL2 script.

    The script should define an async function:
        async def run(inventory_path: str, extravars: dict, on_event: Callable) -> int

    Args:
        script_path: Path to Python script

    Returns:
        The run function, or None if not found
    """
    if not os.path.exists(script_path):
        return None

    try:
        spec = importlib.util.spec_from_file_location("ftl2_script", script_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "run"):
            return module.run

        return None
    except Exception:
        return None


async def execute_script(
    script_path: str,
    inventory_path: str | None,
    extravars: dict[str, Any],
    on_event: Callable[[dict[str, Any]], None],
) -> int:
    """Execute the baked-in FTL2 script.

    Args:
        script_path: Path to Python script
        inventory_path: Path to inventory directory
        extravars: Extra variables dict
        on_event: Event callback

    Returns:
        Exit code (0 = success)
    """
    run_func = load_baked_script(script_path)

    if run_func is None:
        # No script found - emit a simple success event
        on_event({
            "event": "module_start",
            "module": "ftl2_runner",
            "host": "localhost",
        })
        on_event({
            "event": "module_complete",
            "module": "ftl2_runner",
            "host": "localhost",
            "success": True,
            "result": {"msg": f"No script found at {script_path}"},
        })
        return 0

    try:
        result = await run_func(inventory_path, extravars, on_event)
        return result if isinstance(result, int) else 0
    except Exception as e:
        on_event({
            "event": "module_complete",
            "module": "ftl2_runner",
            "host": "localhost",
            "success": False,
            "result": {"msg": str(e)},
        })
        return 1


def run_worker(
    private_data_dir: str,
    keepalive_seconds: int = 0,
    script_path: str = DEFAULT_SCRIPT_PATH,
) -> int:
    """Run the worker process.

    Args:
        private_data_dir: Base directory for job data
        keepalive_seconds: Interval for keepalive events (0 = disabled)
        script_path: Path to baked-in FTL2 script

    Returns:
        Exit code
    """
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    # Read input stream and unpack to private_data_dir
    kwargs = read_input_stream(stdin, private_data_dir)

    # Get identifiers
    ident = get_ident(private_data_dir, kwargs)

    # Setup artifact writer
    artifact_dir = Path(private_data_dir) / "artifacts" / ident
    artifact_writer = ArtifactWriter(artifact_dir, ident)
    artifact_writer.setup()

    # Event counter for status events
    event_counter = 0

    def next_counter() -> int:
        nonlocal event_counter
        event_counter += 1
        return event_counter

    # Send starting status
    write_status(stdout, "starting")

    # Create event translator
    collected_events: list[dict[str, Any]] = []
    stats: dict[str, dict[str, int]] = {}

    def on_translated_event(event: dict[str, Any]) -> None:
        """Handle translated event."""
        # Write to stdout for streaming
        write_event(stdout, event)

        # Write to artifact file
        artifact_writer.write_event(event)

        # Collect for stats
        collected_events.append(event)

        # Update stats
        host = event.get("event_data", {}).get("host", "localhost")
        if host not in stats:
            stats[host] = {"ok": 0, "changed": 0, "failed": 0, "skipped": 0}

        event_type = event.get("event")
        if event_type == "runner_on_ok":
            stats[host]["ok"] += 1
            if event.get("event_data", {}).get("changed"):
                stats[host]["changed"] += 1
        elif event_type == "runner_on_failed":
            stats[host]["failed"] += 1

    translator = EventTranslator(ident, on_event=on_translated_event)

    # Load inventory and extravars
    inventory_path = get_inventory_path(private_data_dir)
    extravars = load_extravars(private_data_dir)

    # Send running status
    write_status(stdout, "running")

    # Execute the script
    try:
        rc = asyncio.run(
            execute_script(script_path, inventory_path, extravars, translator)
        )
    except Exception as e:
        # Error during execution
        write_status(stdout, "error", result_traceback=str(e))
        artifact_writer.write_rc(1)
        artifact_writer.write_status("error")
        write_eof(stdout)
        return 1

    # Determine final status
    if rc == 0:
        status = "successful"
    else:
        status = "failed"

    # Write stats event
    stats_event = create_playbook_stats_event(ident, next_counter(), stats)
    write_event(stdout, stats_event)
    artifact_writer.write_event(stats_event)

    # Write final status
    write_status(stdout, status)

    # Write artifacts
    artifact_writer.write_rc(rc)
    artifact_writer.write_status(status)

    # Stream artifacts back
    stream_dir(str(artifact_dir), stdout)

    # Send EOF
    write_eof(stdout)

    return rc
