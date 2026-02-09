"""Remote ping example for ftl2-runner.

This script demonstrates how to:
- Load inventory from the private_data_dir
- Run modules against remote hosts
- Report per-host results

The script pings all hosts in the inventory.
"""

from pathlib import Path

from ftl2 import automation


async def run(inventory_path: str, extravars: dict, on_event: callable) -> int:
    """Ping all hosts in inventory.

    Args:
        inventory_path: Path to inventory directory
        extravars: Extra variables from AWX
        on_event: Callback to emit events

    Returns:
        Exit code (0 = all hosts reachable, 1 = some failed)
    """
    # Load inventory if provided
    inventory = None
    if inventory_path:
        hosts_file = Path(inventory_path) / "hosts"
        if hosts_file.exists():
            inventory = str(hosts_file)

    failed_hosts = []

    async with automation(inventory=inventory) as ftl:
        # Get all hosts from inventory
        hosts = list(ftl.hosts.keys()) if ftl.hosts else ["localhost"]

        for host in hosts:
            on_event({
                "event": "module_start",
                "module": "ping",
                "host": host,
            })

            try:
                if host == "localhost":
                    result = await ftl.ping()
                else:
                    results = await ftl.run_on(host, "ping")
                    result = results.get(host, {})

                success = result.get("ping") == "pong"

                on_event({
                    "event": "module_complete",
                    "module": "ping",
                    "host": host,
                    "success": success,
                    "changed": False,
                    "result": result,
                })

                if not success:
                    failed_hosts.append(host)

            except Exception as e:
                on_event({
                    "event": "module_complete",
                    "module": "ping",
                    "host": host,
                    "success": False,
                    "changed": False,
                    "result": {"msg": str(e)},
                })
                failed_hosts.append(host)

    return 1 if failed_hosts else 0
