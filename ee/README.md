# FTL2-Runner Execution Environment

This directory contains files for building an AWX-compatible execution environment
that uses FTL2 instead of Ansible for automation.

## Building the Execution Environment

### Quick Build (Recommended)

```bash
cd ee/
docker build -t ftl2-runner-ee:latest -f Containerfile .
```

### Using ansible-builder

If you prefer ansible-builder for more complex EEs:

```bash
pip install ansible-builder
cd ee/
ansible-builder build --tag ftl2-runner-ee:latest --container-runtime docker
```

Note: ansible-builder requires additional configuration for the version 3 format.

## Customizing the Script

The execution environment bakes in a script at `/opt/ftl2/main.py`. To use your
own script:

### Option 1: Replace at build time

Edit `files/example-script.py` before building, or copy your script:

```bash
cp my_automation.py files/example-script.py
ansible-builder build --tag my-ftl2-ee:latest
```

### Option 2: Use environment variable

Set `FTL2_SCRIPT` to override the script path at runtime:

```yaml
# In AWX job template extra variables or EE environment
FTL2_SCRIPT: /runner/project/my_script.py
```

### Option 3: Mount at runtime

In AWX, you can mount scripts via the job template's project:

1. Put your script in the project repository
2. Set `FTL2_SCRIPT=/runner/project/your_script.py` in the job template

## Using with AWX

1. Push the built image to a registry:
   ```bash
   podman push ftl2-runner-ee:latest quay.io/yourorg/ftl2-runner-ee:latest
   ```

2. In AWX, create an Execution Environment pointing to your image

3. Create a Job Template:
   - Set the Execution Environment to your FTL2 EE
   - Extra Variables are passed to the script as `extravars`
   - Inventory is passed as `inventory_path`

## Files

| File | Purpose |
|------|---------|
| `Containerfile` | Docker/Podman build file (recommended) |
| `execution-environment.yml` | ansible-builder definition (alternative) |
| `requirements.txt` | Python dependencies (for ansible-builder) |
| `bindep.txt` | System dependencies (for ansible-builder) |
| `files/example-script.py` | Example FTL2 script (baked into image) |

## How It Works

1. AWX submits work via Receptor
2. Receptor invokes `ansible-runner worker` (symlinked to `ftl2-runner`)
3. ftl2-runner unpacks the job data from stdin
4. ftl2-runner loads the FTL2 script from `/opt/ftl2/main.py`
5. The script runs using FTL2's async automation engine
6. Events stream back to AWX in ansible-runner format

## Script Interface

Scripts must define an async `run` function:

```python
async def run(inventory_path: str, extravars: dict, runner) -> int:
    """Execute FTL2 automation.

    Args:
        inventory_path: Path to inventory directory
        extravars: Extra variables dict from AWX
        runner: RunnerContext for automatic event streaming

    Returns:
        Exit code (0 = success, non-zero = failure)
    """
    async with runner.automation() as ftl:
        await ftl.ping()
        # ... your automation logic
    return 0
```

Events are emitted automatically when modules execute - no manual event handling needed.

## Troubleshooting

### Events not appearing in AWX

Ensure your script uses `runner.automation()` context manager. Events are only
emitted automatically within this context.

### Script not found

Check that either:
- Script is baked in at `/opt/ftl2/main.py`
- `FTL2_SCRIPT` environment variable points to valid path
- Script is mounted via project directory

### Import errors

Ensure FTL2 is installed in the execution environment. Check `requirements.txt`
has the correct ftl2 dependency.
