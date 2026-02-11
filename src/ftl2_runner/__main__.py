"""CLI entry point for ftl2-runner.

This provides a drop-in replacement for ansible-runner's worker command.
Receptor calls: ansible-runner worker --private-data-dir=/runner

Also provides an `adhoc` command for running ad-hoc modules like the `ansible` CLI.
"""

import argparse
import os
import shutil
import sys
import tempfile

import yaml

from ftl2_runner.capacity import get_worker_info
from ftl2_runner.adhoc import create_adhoc_parser, handle_adhoc


def main(args: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ftl2-runner",
        description="FTL2-based replacement for ansible-runner",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Ad-hoc command (mimics ansible CLI)
    create_adhoc_parser(subparsers)

    # Worker command
    worker_parser = subparsers.add_parser(
        "worker",
        help="Execute work streamed from a controlling instance",
    )

    worker_parser.add_argument(
        "--private-data-dir",
        dest="private_data_dir",
        help="Base directory containing job metadata",
    )

    worker_parser.add_argument(
        "--worker-info",
        dest="worker_info",
        action="store_true",
        help="Show execution node info (CPU, memory, version)",
    )

    worker_parser.add_argument(
        "--delete",
        dest="delete_directory",
        action="store_true",
        default=False,
        help="Delete private_data_dir before/after execution",
    )

    worker_parser.add_argument(
        "--keepalive-seconds",
        dest="keepalive_seconds",
        type=int,
        default=0,
        help="Interval for keepalive events",
    )

    # Worker cleanup subcommand
    worker_subparsers = worker_parser.add_subparsers(
        dest="worker_subcommand",
        help="Worker sub-commands",
    )

    cleanup_parser = worker_subparsers.add_parser(
        "cleanup",
        help="Cleanup old job directories",
    )

    cleanup_parser.add_argument(
        "--file-pattern",
        dest="file_pattern",
        default="artifacts/*/",
        help="Glob pattern for directories to clean",
    )

    cleanup_parser.add_argument(
        "--remove-images",
        dest="remove_images",
        action="store_true",
        default=False,
        help="Also remove container images",
    )

    cleanup_parser.add_argument(
        "--grace-period",
        dest="grace_period",
        type=int,
        default=3600,
        help="Only clean items older than this (seconds)",
    )

    parsed = parser.parse_args(args)

    if parsed.command == "worker":
        return handle_worker(parsed)
    elif parsed.command == "adhoc":
        return handle_adhoc(parsed)
    else:
        parser.print_help()
        return 1


def handle_worker(args: argparse.Namespace) -> int:
    """Handle the worker command."""
    # Handle --worker-info
    if args.worker_info:
        info = get_worker_info()
        print(yaml.safe_dump(info, default_flow_style=True), end="")
        return 0

    # Handle cleanup subcommand
    if args.worker_subcommand == "cleanup":
        # Stub - just return success
        return 0

    # Handle delete flag
    private_data_dir = args.private_data_dir
    if private_data_dir and args.delete_directory:
        shutil.rmtree(private_data_dir, ignore_errors=True)

    # Create temp dir if not specified
    if private_data_dir is None:
        private_data_dir = tempfile.mkdtemp(prefix="ftl2_runner_")

    # Ensure directory exists
    os.makedirs(private_data_dir, exist_ok=True)

    # Run the worker
    from ftl2_runner.worker import run_worker, DEFAULT_SCRIPT_PATH

    # Script path from environment or default
    script_path = os.environ.get("FTL2_SCRIPT", DEFAULT_SCRIPT_PATH)

    try:
        rc = run_worker(
            private_data_dir=private_data_dir,
            keepalive_seconds=args.keepalive_seconds,
            script_path=script_path,
        )
    finally:
        # Cleanup if --delete was specified
        if args.delete_directory:
            shutil.rmtree(private_data_dir, ignore_errors=True)

    return rc


if __name__ == "__main__":
    sys.exit(main())
