"""File operations example for ftl2-runner.

This script demonstrates how to:
- Use extravars passed from AWX
- Run multiple modules with automatic event streaming
- All events are emitted automatically by FTL2

The script creates a directory and file based on extravars.
"""


async def run(inventory_path: str, extravars: dict, runner) -> int:
    """Execute file operations based on extravars.

    Expected extravars:
        base_dir: Directory to create (default: /tmp/ftl2-test)
        filename: File to create in base_dir (default: hello.txt)
        content: Content to write (default: "Hello from FTL2!")

    Args:
        inventory_path: Path to inventory directory
        extravars: Extra variables from AWX
        runner: RunnerContext for automatic event streaming

    Returns:
        Exit code (0 = success)
    """
    # Get configuration from extravars with defaults
    base_dir = extravars.get("base_dir", "/tmp/ftl2-test")
    filename = extravars.get("filename", "hello.txt")
    content = extravars.get("content", "Hello from FTL2!")
    file_path = f"{base_dir}/{filename}"

    # All module calls automatically emit events
    async with runner.automation() as ftl:
        # Create directory
        await ftl.file(path=base_dir, state="directory", mode="0755")

        # Create file with content using shell
        escaped_content = content.replace("'", "'\"'\"'")
        await ftl.shell(cmd=f"echo '{escaped_content}' > {file_path}")

        # Verify file exists
        result = await ftl.stat(path=file_path)
        exists = result.get("stat", {}).get("exists", False)

        if not exists:
            return 1

    return 0
