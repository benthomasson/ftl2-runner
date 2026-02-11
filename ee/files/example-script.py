"""Example FTL2 script for execution environment.

Replace this with your actual automation script.
The script receives:
  - inventory_path: Path to inventory directory
  - extravars: Dict of extra variables from AWX job template
  - runner: RunnerContext for automatic event streaming

Events are emitted automatically when you use runner.automation().
"""


async def run(inventory_path: str, extravars: dict, runner) -> int:
    """Execute FTL2 automation.

    Args:
        inventory_path: Path to inventory directory from private_data_dir
        extravars: Extra variables dict from AWX job template
        runner: RunnerContext for automatic event streaming

    Returns:
        Exit code (0 = success, non-zero = failure)
    """
    async with runner.automation() as ftl:
        # Example: ping localhost
        await ftl.ping()

        # Example: create a file if path is provided in extravars
        if "file_path" in extravars:
            await ftl.file(
                path=extravars["file_path"],
                state=extravars.get("file_state", "touch"),
            )

        # Example: run a command if provided
        if "command" in extravars:
            await ftl.command(cmd=extravars["command"])

    return 0
