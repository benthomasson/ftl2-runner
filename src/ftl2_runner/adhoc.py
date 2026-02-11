"""Ad-hoc command execution for ftl2-runner.

This module provides ansible-compatible ad-hoc command execution using FTL2.
It mimics the `ansible` CLI interface for running single modules.

Usage:
    ftl2-runner adhoc -m ping localhost
    ftl2-runner adhoc -m command -a "echo hello" all
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ftl2.automation import automation


def parse_module_args(args_str: str | None) -> dict[str, Any]:
    """Parse module arguments from string format.

    Supports both key=value format and JSON format.
    For free-form modules (command, shell), the entire string is treated as the command.

    Args:
        args_str: Module arguments as "key1=value1 key2=value2" or JSON or free-form

    Returns:
        Dict of module arguments
    """
    if not args_str:
        return {}

    args_str = args_str.strip()

    # Try JSON first
    if args_str.startswith("{"):
        try:
            return json.loads(args_str)
        except json.JSONDecodeError:
            pass

    # Check if this looks like key=value format (has = but not at start)
    # If no = found, treat the whole thing as a free-form command
    if "=" not in args_str:
        return {"_raw_params": args_str}

    # Parse key=value format
    result = {}
    # Simple parser - handles basic key=value pairs
    parts = []
    current = ""
    in_quotes = False
    quote_char = None

    for char in args_str:
        if char in ('"', "'") and not in_quotes:
            in_quotes = True
            quote_char = char
        elif char == quote_char and in_quotes:
            in_quotes = False
            quote_char = None
        elif char == " " and not in_quotes:
            if current:
                parts.append(current)
                current = ""
            continue
        current += char

    if current:
        parts.append(current)

    for part in parts:
        if "=" in part:
            key, _, value = part.partition("=")
            # Strip quotes from value
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            result[key] = value
        else:
            # Positional argument - append to _raw_params
            if "_raw_params" in result:
                result["_raw_params"] += " " + part
            else:
                result["_raw_params"] = part

    return result


async def run_adhoc(
    module: str,
    module_args: dict[str, Any],
    host_pattern: str,
    inventory: str | None = None,
    check_mode: bool = False,
    verbosity: int = 0,
) -> int:
    """Run an ad-hoc command using FTL2.

    Args:
        module: Module name (e.g., "ping", "command", "shell")
        module_args: Module arguments dict
        host_pattern: Host pattern to target
        inventory: Path to inventory file/directory
        check_mode: Run in check mode
        verbosity: Verbosity level

    Returns:
        Exit code (0 = success, non-zero = failure)
    """
    verbose = verbosity > 0

    try:
        async with automation(check_mode=check_mode, verbose=verbose) as ftl:
            # Get the module function
            if not hasattr(ftl, module):
                print(f"ERROR! Module '{module}' not found", file=sys.stderr)
                return 1

            module_func = getattr(ftl, module)

            # Handle special module argument formats
            if module in ("command", "shell", "raw"):
                # These modules use 'cmd' or '_raw_params'
                if "_raw_params" in module_args:
                    module_args["cmd"] = module_args.pop("_raw_params")

            # Execute the module
            try:
                result = await module_func(**module_args)

                # Format output like ansible
                print(f"{host_pattern} | SUCCESS => {{")
                if hasattr(result, "__dict__"):
                    output = result.__dict__
                elif isinstance(result, dict):
                    output = result
                else:
                    output = {"result": str(result)}

                print(f"    {json.dumps(output, indent=4, default=str)}")
                print("}")

                return 0

            except Exception as e:
                print(f"{host_pattern} | FAILED! => {{", file=sys.stderr)
                print(f'    "msg": "{e}"', file=sys.stderr)
                print("}", file=sys.stderr)
                return 1

    except Exception as e:
        print(f"ERROR! {e}", file=sys.stderr)
        return 1


def create_adhoc_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Create the adhoc subcommand parser.

    Args:
        subparsers: Parent subparsers object

    Returns:
        The adhoc parser
    """
    adhoc_parser = subparsers.add_parser(
        "adhoc",
        help="Run ad-hoc commands (like ansible CLI)",
        description="Execute a single module against hosts, similar to the ansible command.",
    )

    adhoc_parser.add_argument(
        "host_pattern",
        nargs="?",
        default="localhost",
        help="Host pattern to target (default: localhost)",
    )

    adhoc_parser.add_argument(
        "-m", "--module-name",
        dest="module",
        default="ping",
        help="Module name to execute (default: ping)",
    )

    adhoc_parser.add_argument(
        "-a", "--args",
        dest="module_args",
        default="",
        help="Module arguments",
    )

    adhoc_parser.add_argument(
        "-i", "--inventory",
        dest="inventory",
        help="Inventory file or directory",
    )

    adhoc_parser.add_argument(
        "-C", "--check",
        dest="check_mode",
        action="store_true",
        help="Run in check mode (dry run)",
    )

    adhoc_parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (use multiple times for more)",
    )

    adhoc_parser.add_argument(
        "-u", "--user",
        dest="remote_user",
        help="Remote user (ignored - FTL2 uses SSH config)",
    )

    adhoc_parser.add_argument(
        "-b", "--become",
        dest="become",
        action="store_true",
        help="Become root (ignored - use FTL2 privilege escalation)",
    )

    adhoc_parser.add_argument(
        "--become-user",
        dest="become_user",
        help="Become this user (ignored)",
    )

    adhoc_parser.add_argument(
        "--become-method",
        dest="become_method",
        help="Become method (ignored)",
    )

    adhoc_parser.add_argument(
        "-f", "--forks",
        dest="forks",
        type=int,
        default=5,
        help="Number of parallel processes (ignored - FTL2 uses async)",
    )

    adhoc_parser.add_argument(
        "--diff",
        dest="diff_mode",
        action="store_true",
        help="Show differences (ignored)",
    )

    adhoc_parser.add_argument(
        "-e", "--extra-vars",
        dest="extra_vars",
        action="append",
        default=[],
        help="Extra variables (ignored - use module args)",
    )

    adhoc_parser.add_argument(
        "--ask-pass",
        dest="ask_pass",
        action="store_true",
        help="Ask for SSH password (ignored)",
    )

    adhoc_parser.add_argument(
        "--ask-become-pass",
        dest="ask_become_pass",
        action="store_true",
        help="Ask for become password (ignored)",
    )

    return adhoc_parser


def handle_adhoc(args: argparse.Namespace) -> int:
    """Handle the adhoc command.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    module_args = parse_module_args(args.module_args)

    return asyncio.run(
        run_adhoc(
            module=args.module,
            module_args=module_args,
            host_pattern=args.host_pattern,
            inventory=args.inventory,
            check_mode=args.check_mode,
            verbosity=args.verbose,
        )
    )
