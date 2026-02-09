"""File operations example for ftl2-runner.

This script demonstrates how to:
- Use extravars passed from AWX
- Run multiple modules
- Report results back via on_event

The script creates a directory and file based on extravars.
"""

from ftl2 import automation


async def run(inventory_path: str, extravars: dict, on_event: callable) -> int:
    """Execute file operations based on extravars.

    Expected extravars:
        base_dir: Directory to create (default: /tmp/ftl2-test)
        filename: File to create in base_dir (default: hello.txt)
        content: Content to write (default: "Hello from FTL2!")

    Args:
        inventory_path: Path to inventory directory
        extravars: Extra variables from AWX
        on_event: Callback to emit events

    Returns:
        Exit code (0 = success)
    """
    # Get configuration from extravars with defaults
    base_dir = extravars.get("base_dir", "/tmp/ftl2-test")
    filename = extravars.get("filename", "hello.txt")
    content = extravars.get("content", "Hello from FTL2!")

    errors = []

    async with automation() as ftl:
        # Step 1: Create directory
        on_event({
            "event": "module_start",
            "module": "file",
            "host": "localhost",
        })

        try:
            result = await ftl.file(path=base_dir, state="directory", mode="0755")
            on_event({
                "event": "module_complete",
                "module": "file",
                "host": "localhost",
                "success": True,
                "changed": result.get("changed", False),
                "result": result,
            })
        except Exception as e:
            on_event({
                "event": "module_complete",
                "module": "file",
                "host": "localhost",
                "success": False,
                "changed": False,
                "result": {"msg": str(e)},
            })
            errors.append(str(e))

        # Step 2: Create file with content using shell
        file_path = f"{base_dir}/{filename}"

        on_event({
            "event": "module_start",
            "module": "shell",
            "host": "localhost",
        })

        try:
            # Use shell to write content (escaping for safety)
            escaped_content = content.replace("'", "'\"'\"'")
            result = await ftl.shell(cmd=f"echo '{escaped_content}' > {file_path}")
            on_event({
                "event": "module_complete",
                "module": "shell",
                "host": "localhost",
                "success": True,
                "changed": True,
                "result": {"dest": file_path, "content_length": len(content)},
            })
        except Exception as e:
            on_event({
                "event": "module_complete",
                "module": "shell",
                "host": "localhost",
                "success": False,
                "changed": False,
                "result": {"msg": str(e)},
            })
            errors.append(str(e))

        # Step 3: Verify file exists
        on_event({
            "event": "module_start",
            "module": "stat",
            "host": "localhost",
        })

        try:
            result = await ftl.stat(path=file_path)
            exists = result.get("stat", {}).get("exists", False)
            on_event({
                "event": "module_complete",
                "module": "stat",
                "host": "localhost",
                "success": exists,
                "changed": False,
                "result": {
                    "path": file_path,
                    "exists": exists,
                    "size": result.get("stat", {}).get("size", 0),
                },
            })
            if not exists:
                errors.append(f"File {file_path} was not created")
        except Exception as e:
            on_event({
                "event": "module_complete",
                "module": "stat",
                "host": "localhost",
                "success": False,
                "changed": False,
                "result": {"msg": str(e)},
            })
            errors.append(str(e))

    return 1 if errors else 0
