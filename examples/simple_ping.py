"""Simple ping example for ftl2-runner.

This script demonstrates the basic structure of an FTL2 script
that can be executed by ftl2-runner.

Usage:
    # Test directly
    python -c "
    import asyncio
    from examples.simple_ping import run

    events = []
    rc = asyncio.run(run(None, {}, events.append))
    print(f'RC: {rc}')
    for e in events:
        print(e)
    "

    # Or via ftl2-runner worker
    from ftl2_runner.worker import run_worker
    run_worker('/tmp/work', 0, 'examples/simple_ping.py')
"""

from ftl2 import automation


async def run(inventory_path: str, extravars: dict, on_event: callable) -> int:
    """Execute a simple ping test.

    Args:
        inventory_path: Path to inventory directory (unused in this example)
        extravars: Extra variables from AWX
        on_event: Callback to emit events

    Returns:
        Exit code (0 = success)
    """
    on_event({
        "event": "module_start",
        "module": "ping",
        "host": "localhost",
    })

    try:
        async with automation() as ftl:
            result = await ftl.ping()

        on_event({
            "event": "module_complete",
            "module": "ping",
            "host": "localhost",
            "success": True,
            "changed": False,
            "result": result,
        })
        return 0

    except Exception as e:
        on_event({
            "event": "module_complete",
            "module": "ping",
            "host": "localhost",
            "success": False,
            "changed": False,
            "result": {"msg": str(e)},
        })
        return 1
