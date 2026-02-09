# CLAUDE.md - Project Instructions for Claude

## Project Overview

ftl2-runner is a drop-in replacement for ansible-runner's worker mode that uses FTL2 as the execution backend. It enables AWX/AAP to leverage FTL2's performance improvements without code changes.

## Key Concepts

- **Worker Mode**: The primary interface - called by Receptor via CLI
- **Streaming Protocol**: Line-delimited JSON over stdin/stdout for communication with Receptor
- **Baked-in Script**: FTL2 script at `/opt/ftl2/main.py` that gets executed (ignores playbooks from AWX)
- **Event Translation**: Converts FTL2 events to ansible-runner format

## Project Structure

```
ftl2-runner/
├── src/ftl2_runner/
│   ├── __init__.py      # Public exports
│   ├── __main__.py      # CLI entry point
│   ├── worker.py        # Main worker logic
│   ├── streaming.py     # Stdin/stdout protocol
│   ├── events.py        # Event translation (FTL2 -> ansible-runner)
│   ├── artifacts.py     # Artifact file management
│   └── capacity.py      # --worker-info implementation
├── tests/
│   ├── test_worker_streaming.py      # Unit tests (no Receptor)
│   └── test_receptor_integration.py  # Integration tests (requires Receptor)
└── docs/
    ├── ftl2-runner-design.md  # Architecture documentation
    └── receptor-test.md       # Manual Receptor testing guide
```

## Development Commands

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_worker_streaming.py -v

# Test CLI
uv run ftl2-runner worker --worker-info
```

## Related Projects

- **FTL2**: `/Users/ben/git/faster-than-light2` - The execution engine
- **ansible-runner**: `/Users/ben/git/ansible-runner` - Reference implementation
- **Receptor**: `/Users/ben/git/receptor` - Mesh networking that calls ftl2-runner
- **AWX**: `/Users/ben/git/awx` - Controller that uses Receptor

## Testing with Receptor

Receptor binary must be built from source:
```bash
cd /Users/ben/git/receptor
make receptor
```

The integration tests auto-discover the Receptor binary and skip if not found.

## Streaming Protocol Format

**Input (stdin):**
```
{"kwargs": {"ident": "job-123"}}
{"zipfile": 1234}
<base64 encoded zip of private_data_dir>
{"eof": true}
```

**Output (stdout):**
```
{"status": "starting"}
{"status": "running"}
{"event": "runner_on_start", ...}
{"event": "runner_on_ok", ...}
{"event": "playbook_on_stats", ...}
{"status": "successful"}
{"zipfile": 5678}
<base64 encoded zip of artifacts>
{"eof": true}
```

## FTL2 Script Interface

Scripts must implement:
```python
async def run(inventory_path: str, extravars: dict, on_event: callable) -> int:
    # inventory_path: Path to inventory directory
    # extravars: Dict from private_data_dir/env/extravars
    # on_event: Callback for {"event": "module_start|module_complete", ...}
    # Returns: exit code (0 = success)
```

## Common Issues

- **Unix socket path too long**: Use `/tmp/` for socket files (104 char limit on macOS)
- **Python version**: Requires 3.13+ (FTL2 requirement)
- **ftl2 dependency**: Installed from git, not PyPI
