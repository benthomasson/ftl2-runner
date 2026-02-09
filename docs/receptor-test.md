# Testing ftl2-runner with Receptor

This guide explains how to test ftl2-runner with Receptor to verify the streaming protocol works correctly.

## Prerequisites

- Python 3.13+
- Go 1.21+ (for building Receptor)
- uv (Python package manager)

## Setup

### 1. Install ftl2-runner

```bash
cd /Users/ben/git/ftl2-runner
uv venv
uv pip install -e ".[dev]"
uv pip install receptorctl
```

### 2. Build Receptor

```bash
cd /Users/ben/git/receptor
make receptor
cp receptor /usr/local/bin/  # or add to PATH
```

### 3. Create Test Files

Create the following files in `/tmp/`:

**`/tmp/receptor.yaml`** - Receptor configuration:
```yaml
---
- node:
    id: test-node

- log-level:
    level: debug

- tcp-listener:
    port: 2223

- control-service:
    service: control
    filename: /tmp/ftl2-receptor.sock

- work-command:
    worktype: ansible-runner
    command: /tmp/run_worker.sh
    allowruntimeparams: false
```

**`/tmp/run_worker.sh`** - Worker wrapper script:
```bash
#!/bin/bash
export PATH="/Users/ben/git/ftl2-runner/.venv/bin:$PATH"
export PYTHONPATH="/Users/ben/git/ftl2-runner/src"

python -c "
import sys
from ftl2_runner.worker import run_worker
sys.exit(run_worker(
    '/tmp/ftl2-receptor-work',
    0,
    '/tmp/ftl2_script.py'
))
"
```

**`/tmp/ftl2_script.py`** - Test FTL2 script:
```python
"""Test FTL2 script for receptor testing."""

async def run(inventory_path, extravars, on_event):
    on_event({
        "event": "module_start",
        "module": "receptor_test",
        "host": "localhost",
    })
    on_event({
        "event": "module_complete",
        "module": "receptor_test",
        "host": "localhost",
        "success": True,
        "changed": False,
        "result": {
            "msg": f"Receptor test passed! extravars={extravars}",
            "inventory_path": inventory_path,
        },
    })
    return 0
```

**`/tmp/create_payload.py`** - Payload generator:
```python
#!/usr/bin/env python3
import base64, io, json, os, sys, tempfile, zipfile
from pathlib import Path

def create_private_data_dir(base_dir):
    (base_dir / "inventory").mkdir(parents=True)
    (base_dir / "env").mkdir(parents=True)
    (base_dir / "inventory" / "hosts").write_text("[all]\nlocalhost ansible_connection=local\n")
    (base_dir / "env" / "extravars").write_text(json.dumps({"test_var": "hello"}))

def create_payload(source_dir, kwargs):
    output = io.BytesIO()
    output.write(json.dumps({"kwargs": kwargs}).encode() + b"\n")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for f in files:
                p = Path(root) / f
                zf.write(p, p.relative_to(source_dir))

    zip_data = zip_buf.getvalue()
    output.write(json.dumps({"zipfile": len(zip_data)}).encode() + b"\n")
    output.write(base64.b64encode(zip_data) + b"\n")
    output.write(json.dumps({"eof": True}).encode() + b"\n")
    return output.getvalue()

with tempfile.TemporaryDirectory() as tmp:
    src = Path(tmp) / "source"
    create_private_data_dir(src)
    sys.stdout.buffer.write(create_payload(src, {"ident": "test-123"}))
```

### 4. Make Scripts Executable

```bash
chmod +x /tmp/run_worker.sh
mkdir -p /tmp/ftl2-receptor-work
```

## Running the Test

### 1. Start Receptor

```bash
# Clean up any old socket
rm -f /tmp/ftl2-receptor.sock

# Start Receptor (in background)
receptor -c /tmp/receptor.yaml &

# Verify it's running
ls -la /tmp/ftl2-receptor.sock
```

### 2. Generate Payload

```bash
cd /Users/ben/git/ftl2-runner
uv run python /tmp/create_payload.py > /tmp/work_payload.bin
```

### 3. Submit Work

```bash
uv run receptorctl \
    --socket /tmp/ftl2-receptor.sock \
    work submit ansible-runner \
    --node test-node \
    --payload /tmp/work_payload.bin \
    --follow
```

### 4. Expected Output

```json
{"status": "starting"}
{"status": "running"}
{"uuid": "...", "event": "runner_on_start", "event_data": {"host": "localhost", "task": "receptor_test"}}
{"uuid": "...", "event": "runner_on_ok", "event_data": {"host": "localhost", "res": {"msg": "Receptor test passed! extravars={'test_var': 'hello'}"}}}
{"uuid": "...", "event": "playbook_on_stats", "event_data": {"stats": {"localhost": {"ok": 1, "changed": 0, "failed": 0, "skipped": 0}}}}
{"status": "successful"}
{"zipfile": 1655}
<base64 encoded artifacts>
{"eof": true}
```

### 5. Cleanup

```bash
pkill -f "receptor -c /tmp/receptor.yaml"
rm -f /tmp/ftl2-receptor.sock
```

## Troubleshooting

### Receptor exits immediately
Add a `tcp-listener` to the config - Receptor needs at least one backend to stay running.

### "No such file or directory" errors
Ensure all paths in the config and scripts are absolute paths.

### receptorctl version warning
The warning about version mismatch is usually safe to ignore for basic testing.

### Socket permission denied
The socket is created with user-only permissions. Make sure you're running receptorctl as the same user that started Receptor.

## Automated Test

For CI/automated testing, use the pytest test instead:

```bash
cd /Users/ben/git/ftl2-runner
uv run pytest tests/test_worker_streaming.py -v
```

This runs the same streaming protocol test without requiring Receptor.
