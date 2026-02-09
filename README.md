# ftl2-runner

A drop-in replacement for [ansible-runner](https://github.com/ansible/ansible-runner)'s worker mode that uses [FTL2](https://github.com/benthomasson/ftl2) as the execution backend.

## Overview

ftl2-runner enables AWX/AAP to use FTL2 for job execution by implementing the ansible-runner worker protocol. When deployed in an execution environment, Receptor calls ftl2-runner instead of ansible-runner, and ftl2-runner executes a baked-in FTL2 script while emitting ansible-runner compatible events.

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐     ┌──────────────┐
│ AWX/AAP     │────▶│ Receptor │────▶│ ftl2-runner │────▶│ FTL2 Script  │
│ Controller  │     │          │     │ (worker)    │     │ /opt/ftl2/   │
└─────────────┘     └──────────┘     └─────────────┘     └──────────────┘
                         │                  │
                         │    streaming     │
                         │◀─────events──────│
```

## Requirements

- Python 3.13+
- [FTL2](https://github.com/benthomasson/ftl2)

## Installation

```bash
# From source
pip install -e .

# With uv
uv pip install -e .
```

## Usage

### Worker Mode (Receptor Integration)

ftl2-runner is designed to be called by Receptor as a work-command:

```yaml
# receptor.yaml
- work-command:
    worktype: ansible-runner
    command: ftl2-runner
    params: "worker --private-data-dir=/runner"
```

The worker:
1. Receives streaming input via stdin (kwargs + zipped private_data_dir)
2. Unpacks inventory and extravars
3. Executes the baked-in FTL2 script at `/opt/ftl2/main.py`
4. Streams ansible-runner compatible events to stdout
5. Returns artifacts as a zipped stream

### Worker Info

Get execution node capacity information:

```bash
ftl2-runner worker --worker-info
# Output: {cpu_count: 8, mem_in_bytes: 17179869184, runner_version: 0.1.0, uuid: ...}
```

### Custom Script Path

For development/testing, specify a custom FTL2 script:

```python
from ftl2_runner.worker import run_worker

run_worker(
    private_data_dir="/tmp/work",
    keepalive_seconds=0,
    script_path="/path/to/my_script.py",
)
```

## FTL2 Script Format

The baked-in script must define an async `run` function:

```python
async def run(inventory_path: str, extravars: dict, on_event: callable) -> int:
    """Execute FTL2 automation.

    Args:
        inventory_path: Path to inventory directory
        extravars: Extra variables from AWX
        on_event: Callback to emit events

    Returns:
        Exit code (0 = success)
    """
    on_event({
        "event": "module_start",
        "module": "my_module",
        "host": "localhost",
    })

    # Do work...

    on_event({
        "event": "module_complete",
        "module": "my_module",
        "host": "localhost",
        "success": True,
        "changed": False,
        "result": {"msg": "Done"},
    })

    return 0
```

## Event Translation

FTL2 events are translated to ansible-runner format:

| FTL2 Event | ansible-runner Event |
|------------|---------------------|
| `module_start` | `runner_on_start` |
| `module_complete` (success=True) | `runner_on_ok` |
| `module_complete` (success=False) | `runner_on_failed` |

## Testing

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run all tests
uv run pytest tests/ -v

# Run only streaming protocol tests (no Receptor required)
uv run pytest tests/test_worker_streaming.py -v

# Run Receptor integration tests (requires Receptor binary)
uv run pytest tests/test_receptor_integration.py -v
```

See [docs/receptor-test.md](docs/receptor-test.md) for manual Receptor testing instructions.

## Documentation

- [Design Document](docs/ftl2-runner-design.md) - Architecture and implementation details
- [Receptor Testing](docs/receptor-test.md) - Manual testing with Receptor

## Current Scope

**Implemented:**
- Worker CLI compatible with Receptor work-command
- Streaming protocol (stdin/stdout)
- Event translation to ansible-runner format
- Artifact streaming
- Worker info endpoint

**Not Implemented:**
- Full ansible-runner Python API (`run()`, `run_async()`, etc.)
- Playbook execution (FTL2 executes baked-in scripts only)
- Process isolation / containerization
- Vault / encrypted variables

## License

Apache-2.0
