# ftl2-runner

A drop-in replacement for [ansible-runner](https://github.com/ansible/ansible-runner) that uses [FTL2](https://github.com/your-repo/faster-than-light2) as the execution backend.

## Overview

ftl2-runner provides API compatibility with ansible-runner, enabling AWX and other tools to leverage FTL2's 3-17x performance improvement without code changes.

## Installation

```bash
pip install ftl2-runner
```

## Usage

```python
from ftl2_runner import run

# Ad-hoc module execution
r = run(
    private_data_dir="/tmp/runner",
    module="ping",
    host_pattern="localhost",
)

print(f"Status: {r.status}")
print(f"Return code: {r.rc}")

for event in r.events:
    print(event)
```

## API Compatibility

ftl2-runner implements the core ansible-runner interface:

- `run(**kwargs)` - Synchronous execution
- `run_async(**kwargs)` - Async execution in thread
- `init_runner(**kwargs)` - Initialize without running
- `Runner` class with `status`, `rc`, `events`, `stdout`, `stderr`, `stats`

## Current Scope

**Supported:**
- Ad-hoc module execution (`module` + `module_args`)
- Event callbacks
- Artifact directory structure

**Not Yet Supported:**
- Playbook execution (FTL2 executes modules directly)
- Roles and collections
- Process isolation / containerization
- Vault / encrypted variables

## Documentation

See [docs/ftl2-runner-design.md](docs/ftl2-runner-design.md) for architecture details.

## License

Apache-2.0
