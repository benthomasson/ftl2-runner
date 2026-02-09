"""Remote ping example for ftl2-runner.

This script demonstrates how to:
- Load inventory from the private_data_dir
- Run modules against remote hosts
- Events are emitted automatically for each host

The script pings all hosts in the inventory.
"""

from pathlib import Path


async def run(inventory_path: str, extravars: dict, runner) -> int:
    """Ping all hosts in inventory.

    Args:
        inventory_path: Path to inventory directory
        extravars: Extra variables from AWX
        runner: RunnerContext for automatic event streaming

    Returns:
        Exit code (0 = all hosts reachable, 1 = some failed)
    """
    # Load inventory if provided
    inventory = None
    if inventory_path:
        hosts_file = Path(inventory_path) / "hosts"
        if hosts_file.exists():
            inventory = str(hosts_file)

    # Events are emitted automatically for each module call
    async with runner.automation(inventory=inventory) as ftl:
        # Get all hosts from inventory
        hosts = list(ftl.hosts.keys()) if ftl.hosts else ["localhost"]

        for host in hosts:
            if host == "localhost":
                await ftl.ping()
            else:
                await ftl.run_on(host, "ping")

        # Check if any hosts failed
        if ftl.failed:
            return 1

    return 0
