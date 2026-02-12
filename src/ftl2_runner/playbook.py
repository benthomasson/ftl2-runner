"""Ansible-playbook compatible command for ftl2-runner.

This module provides an ansible-playbook drop-in that executes the
playbook file as a FTL2 Python script. AWX calls ansible-playbook
inside the EE container; this intercepts that call.

Usage:
    ftl2-runner playbook [ansible-playbook args] <playbook.yml>
    ansible-playbook [args] <playbook.yml>  # via symlink/wrapper
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from ftl2_runner.events import encode_event_ansi
from ftl2_runner.runner_context import RunnerContext
from ftl2_runner.worker import load_baked_script


def parse_extravars(extra_vars_list: list[str]) -> dict[str, Any]:
    """Parse extra variables from -e/--extra-vars arguments.

    Supports:
        -e @/path/to/file (JSON file)
        -e '{"key": "value"}' (inline JSON)
        -e key=value (simple key-value)

    Args:
        extra_vars_list: List of -e argument values

    Returns:
        Merged dict of extra variables
    """
    result = {}

    for item in extra_vars_list:
        if item.startswith("@"):
            # File reference
            path = Path(item[1:])
            if path.exists():
                try:
                    content = path.read_text()
                    result.update(json.loads(content))
                except (json.JSONDecodeError, IOError):
                    pass
        elif item.startswith("{"):
            # Inline JSON
            try:
                result.update(json.loads(item))
            except json.JSONDecodeError:
                pass
        elif "=" in item:
            # key=value
            key, _, value = item.partition("=")
            result[key] = value

    return result


async def run_playbook(
    playbook_path: str,
    inventory: str | None = None,
    extra_vars: dict[str, Any] | None = None,
    check_mode: bool = False,
    verbosity: int = 0,
) -> int:
    """Run a playbook file as a FTL2 script.

    Args:
        playbook_path: Path to the playbook/script file
        inventory: Path to inventory file/directory
        extra_vars: Extra variables dict
        check_mode: Run in check mode
        verbosity: Verbosity level

    Returns:
        Exit code (0 = success)
    """
    extra_vars = extra_vars or {}

    # Load the playbook as a Python module
    run_func = load_baked_script(playbook_path)
    if run_func is None:
        print(f"ERROR: Could not load script from {playbook_path}", file=sys.stderr)
        return 1

    # Event handler that encodes events as ANSI escape sequences.
    # AWX's OutputEventFilter extracts these to build structured job events.
    # On terminals, the cursor-backward codes make the encoding invisible.
    def on_event(event: dict[str, Any]) -> None:
        # Build event dict for ANSI encoding (same fields as awx_display get_begin_dict)
        encoded: dict[str, Any] = {
            "event": event.get("event", "verbose"),
            "uuid": event.get("uuid"),
            "created": event.get("created"),
            "event_data": event.get("event_data", {}),
            "pid": os.getpid(),
        }
        if event.get("parent_uuid"):
            encoded["parent_uuid"] = event["parent_uuid"]
        job_id = os.environ.get("JOB_ID", "")
        if job_id:
            encoded["job_id"] = int(job_id)

        # Write ANSI begin marker
        sys.stdout.write(encode_event_ansi(encoded))

        # Write visible stdout text (becomes event's stdout via OutputEventFilter)
        stdout_text = event.get("stdout", "")
        if stdout_text:
            sys.stdout.write(stdout_text)
            if not stdout_text.endswith("\n"):
                sys.stdout.write("\n")

        # Write ANSI end marker (same data, matches awx_display pattern)
        sys.stdout.write(encode_event_ansi(encoded))
        sys.stdout.flush()

    # Create runner context
    runner = RunnerContext(ident="1", on_event=on_event)

    try:
        result = await run_func(inventory, extra_vars, runner)
        runner.emit_stats()
        return result if isinstance(result, int) else 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def create_playbook_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create the playbook subcommand parser.

    Accepts all common ansible-playbook arguments for compatibility.
    """
    pb_parser = subparsers.add_parser(
        "playbook",
        help="Run a playbook as a FTL2 script (ansible-playbook compatible)",
        description="Execute a playbook file as a FTL2 Python script.",
    )

    pb_parser.add_argument(
        "playbook",
        help="Playbook file to execute (will be loaded as a Python script)",
    )

    pb_parser.add_argument(
        "-i", "--inventory",
        dest="inventory",
        help="Inventory file or directory",
    )

    pb_parser.add_argument(
        "-e", "--extra-vars",
        dest="extra_vars",
        action="append",
        default=[],
        help="Extra variables (key=value, JSON, or @file)",
    )

    pb_parser.add_argument(
        "-C", "--check",
        dest="check_mode",
        action="store_true",
        help="Run in check mode (dry run)",
    )

    pb_parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity",
    )

    # Accepted but ignored arguments for ansible-playbook compatibility
    for flag, dest in [
        ("-u", "remote_user"),
        ("--become-user", "become_user"),
        ("--become-method", "become_method"),
        ("--vault-password-file", "vault_password_file"),
        ("--vault-id", "vault_id"),
        ("--syntax-check", "syntax_check"),
        ("--list-tasks", "list_tasks"),
        ("--list-tags", "list_tags"),
        ("--list-hosts", "list_hosts"),
        ("--start-at-task", "start_at_task"),
        ("--skip-tags", "skip_tags"),
        ("-t", "tags"),
        ("-l", "limit"),
    ]:
        pb_parser.add_argument(flag, dest=dest, default=None, help=argparse.SUPPRESS)

    for flag, dest in [
        ("-b", "become"),
        ("--become", "become"),
        ("--diff", "diff_mode"),
        ("--ask-pass", "ask_pass"),
        ("--ask-become-pass", "ask_become_pass"),
        ("--ask-vault-pass", "ask_vault_pass"),
    ]:
        pb_parser.add_argument(flag, dest=dest, action="store_true", default=False, help=argparse.SUPPRESS)

    pb_parser.add_argument(
        "-f", "--forks",
        dest="forks",
        type=int,
        default=5,
        help=argparse.SUPPRESS,
    )

    return pb_parser


def handle_playbook(args: argparse.Namespace) -> int:
    """Handle the playbook command."""
    extra_vars = parse_extravars(args.extra_vars)

    return asyncio.run(
        run_playbook(
            playbook_path=args.playbook,
            inventory=args.inventory,
            extra_vars=extra_vars,
            check_mode=args.check_mode,
            verbosity=args.verbose,
        )
    )
