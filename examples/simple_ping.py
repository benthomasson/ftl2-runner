"""Simple ping example for ftl2-runner.

This script demonstrates the new RunnerContext interface where
events are emitted automatically by FTL2's automation context.

Usage:
    # Via ftl2-runner worker
    from ftl2_runner.worker import run_worker
    run_worker('/tmp/work', 0, 'examples/simple_ping.py')
"""


async def run(inventory_path: str, extravars: dict, runner) -> int:
    """Execute a simple ping test.

    Args:
        inventory_path: Path to inventory directory (unused in this example)
        extravars: Extra variables from AWX
        runner: RunnerContext for automatic event streaming

    Returns:
        Exit code (0 = success)
    """
    # Events are emitted automatically when modules execute
    async with runner.automation() as ftl:
        await ftl.ping()

    return 0
