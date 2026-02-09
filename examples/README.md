# ftl2-runner Examples

Example FTL2 scripts that can be executed by ftl2-runner.

## Script Structure (v0.2+)

Scripts receive a `RunnerContext` that provides automatic event streaming:

```python
async def run(inventory_path: str, extravars: dict, runner) -> int:
    """Execute FTL2 automation.

    Args:
        inventory_path: Path to inventory directory from private_data_dir
        extravars: Extra variables dict from private_data_dir/env/extravars
        runner: RunnerContext for automatic event streaming

    Returns:
        Exit code (0 = success, non-zero = failure)
    """
    async with runner.automation() as ftl:
        await ftl.ping()
    return 0
```

Events are emitted automatically when modules execute - no manual `on_event()` calls needed.

## Examples

### simple_ping.py

Basic example that runs a local ping.

```bash
# Test via worker
uv run python -c "
import sys
sys.path.insert(0, 'src')
from ftl2_runner.worker import run_worker
run_worker('/tmp/work', 0, 'examples/simple_ping.py')
" < /dev/null
```

### file_operations.py

Creates directories and files based on extravars.

### remote_ping.py

Pings all hosts in the inventory.

## Custom Events

For script-specific progress events (not module calls), use `runner.emit_event()`:

```python
async def run(inventory_path, extravars, runner):
    runner.emit_event({
        "event": "custom_progress",
        "message": "Starting phase 1...",
    })

    async with runner.automation() as ftl:
        await ftl.ping()

    return 0
```

## Baking into Execution Environment

For production, add to your execution environment Containerfile:

```dockerfile
FROM quay.io/ansible/ansible-runner:latest

# Install ftl2-runner
COPY ftl2-runner /opt/ftl2-runner
RUN pip install /opt/ftl2-runner

# Install your FTL2 script
COPY my_script.py /opt/ftl2/main.py

# Replace ansible-runner with ftl2-runner
RUN ln -sf /usr/local/bin/ftl2-runner /usr/bin/ansible-runner
```
