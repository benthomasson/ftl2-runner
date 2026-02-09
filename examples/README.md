# ftl2-runner Examples

Example FTL2 scripts that can be executed by ftl2-runner.

## Script Structure

All scripts must implement an async `run` function:

```python
async def run(inventory_path: str, extravars: dict, on_event: callable) -> int:
    """Execute FTL2 automation.

    Args:
        inventory_path: Path to inventory directory from private_data_dir
        extravars: Extra variables dict from private_data_dir/env/extravars
        on_event: Callback to emit events in FTL2 format

    Returns:
        Exit code (0 = success, non-zero = failure)
    """
    pass
```

## Event Format

Events emitted via `on_event()` should follow this structure:

```python
# Module starting
on_event({
    "event": "module_start",
    "module": "module_name",
    "host": "hostname",
})

# Module completed successfully
on_event({
    "event": "module_complete",
    "module": "module_name",
    "host": "hostname",
    "success": True,
    "changed": False,  # or True if something changed
    "result": {"key": "value"},  # module-specific result
})

# Module failed
on_event({
    "event": "module_complete",
    "module": "module_name",
    "host": "hostname",
    "success": False,
    "changed": False,
    "result": {"msg": "Error message"},
})
```

## Examples

### simple_ping.py

Basic example that runs a local ping.

```bash
# Test directly
cd /Users/ben/git/ftl2-runner
uv run python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from examples.simple_ping import run

events = []
rc = asyncio.run(run(None, {}, events.append))
print(f'RC: {rc}')
for e in events:
    print(e)
"
```

### file_operations.py

Creates directories and files based on extravars.

```bash
# Test with extravars
uv run python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from examples.file_operations import run

extravars = {
    'base_dir': '/tmp/my-test',
    'filename': 'test.txt',
    'content': 'Hello World!',
}

events = []
rc = asyncio.run(run(None, extravars, events.append))
print(f'RC: {rc}')
for e in events:
    print(f'{e[\"module\"]}: success={e.get(\"success\", \"?\")}')
"
```

### remote_ping.py

Pings all hosts in the inventory.

```bash
# Create test inventory
mkdir -p /tmp/test-inventory
echo -e "[webservers]\nweb1.example.com\nweb2.example.com" > /tmp/test-inventory/hosts

# Test with inventory
uv run python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from examples.remote_ping import run

events = []
rc = asyncio.run(run('/tmp/test-inventory', {}, events.append))
print(f'RC: {rc}')
for e in events:
    if 'success' in e:
        print(f'{e[\"host\"]}: {\"OK\" if e[\"success\"] else \"FAILED\"}')
"
```

## Using with ftl2-runner Worker

To use these scripts with ftl2-runner in a real deployment:

1. Copy the script to `/opt/ftl2/main.py` in your execution environment
2. Configure Receptor to call ftl2-runner
3. AWX will stream inventory and extravars to the worker

```bash
# Test locally with ftl2-runner worker
uv run python -c "
import sys
sys.path.insert(0, 'src')
from ftl2_runner.worker import run_worker
rc = run_worker(
    '/tmp/ftl2-work',
    0,
    'examples/simple_ping.py',
)
print(f'Worker RC: {rc}')
" < /dev/null
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
