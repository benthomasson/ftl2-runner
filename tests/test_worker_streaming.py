"""Test the worker streaming protocol.

This simulates what Receptor/AWX does:
1. Create a private_data_dir with inventory and extravars
2. Stream it as a zip to the worker via stdin
3. Capture the event output from stdout
4. Verify events are in ansible-runner format
"""

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def create_test_private_data_dir(base_dir: Path) -> None:
    """Create a mock private_data_dir structure."""
    # Create directories
    (base_dir / "inventory").mkdir(parents=True)
    (base_dir / "env").mkdir(parents=True)
    (base_dir / "project").mkdir(parents=True)
    (base_dir / "artifacts").mkdir(parents=True)

    # Create inventory file
    inventory = """[all]
localhost ansible_connection=local
"""
    (base_dir / "inventory" / "hosts").write_text(inventory)

    # Create extravars
    extravars = {"test_var": "hello", "target": "world"}
    (base_dir / "env" / "extravars").write_text(json.dumps(extravars))

    # Create a dummy playbook (will be ignored)
    (base_dir / "project" / "site.yml").write_text("- hosts: all\n  tasks: []")


def create_test_ftl2_script(script_path: Path) -> None:
    """Create a simple test FTL2 script using new RunnerContext interface."""
    script = '''
"""Test FTL2 script for worker testing."""

async def run(inventory_path, extravars, runner):
    """Simple test using automatic event streaming."""
    # Events are emitted automatically by FTL2 automation context
    async with runner.automation() as ftl:
        await ftl.ping()
    return 0
'''
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script)


def create_streaming_input(source_dir: Path, kwargs: dict) -> bytes:
    """Create the streaming input that would come from Receptor.

    Format:
    1. {"kwargs": {...}}\n
    2. {"zipfile": N}\n + base64 encoded zip data
    3. {"eof": true}\n
    """
    output = io.BytesIO()

    # 1. Write kwargs
    output.write(json.dumps({"kwargs": kwargs}).encode("utf-8") + b"\n")

    # 2. Create and write zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                arc_name = file_path.relative_to(source_dir)
                zf.write(file_path, arc_name)

    zip_data = zip_buffer.getvalue()
    zip_size = len(zip_data)

    output.write(json.dumps({"zipfile": zip_size}).encode("utf-8") + b"\n")
    output.write(base64.b64encode(zip_data))

    # 3. Write EOF
    output.write(b"\n")
    output.write(json.dumps({"eof": True}).encode("utf-8") + b"\n")

    return output.getvalue()


def parse_streaming_output(output: bytes) -> list[dict]:
    """Parse the streaming output from the worker.

    Returns list of parsed JSON objects (events, status, etc.)
    """
    events = []
    for line in output.decode("utf-8", errors="replace").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            events.append(event)
        except json.JSONDecodeError:
            # Skip non-JSON lines (like base64 zip data)
            pass
    return events


def test_worker_streaming():
    """Test the full worker streaming flow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create source private_data_dir
        source_dir = tmpdir / "source"
        create_test_private_data_dir(source_dir)

        # Create test FTL2 script
        script_path = tmpdir / "opt" / "ftl2" / "main.py"
        create_test_ftl2_script(script_path)

        # Create target private_data_dir for worker
        target_dir = tmpdir / "runner"
        target_dir.mkdir()

        # Create streaming input
        kwargs = {"ident": "test123"}
        streaming_input = create_streaming_input(source_dir, kwargs)

        print(f"Created streaming input: {len(streaming_input)} bytes")
        print(f"Source dir contents: {list(source_dir.rglob('*'))}")
        print(f"Test script at: {script_path}")

        # Run the worker with custom script path
        env = os.environ.copy()
        env["FTL2_SCRIPT_PATH"] = str(script_path)  # For future enhancement

        result = subprocess.run(
            [
                sys.executable, "-c",
                f"""
import sys
sys.path.insert(0, 'src')
from ftl2_runner.worker import run_worker
rc = run_worker(
    private_data_dir='{target_dir}',
    keepalive_seconds=0,
    script_path='{script_path}',
)
sys.exit(rc)
"""
            ],
            input=streaming_input,
            capture_output=True,
            env=env,
            cwd=str(Path(__file__).parent.parent),
        )

        print(f"\n=== STDOUT ({len(result.stdout)} bytes) ===")
        print(result.stdout.decode("utf-8", errors="replace")[:2000])

        if result.stderr:
            print(f"\n=== STDERR ===")
            print(result.stderr.decode("utf-8", errors="replace"))

        print(f"\n=== Return code: {result.returncode} ===")

        # Parse output
        events = parse_streaming_output(result.stdout)
        print(f"\n=== Parsed {len(events)} events ===")
        for i, event in enumerate(events):
            print(f"{i}: {event}")

        # Verify we got expected event types
        event_types = [e.get("event") or e.get("status") for e in events]
        print(f"\nEvent types: {event_types}")

        # Check for status events
        assert any(e.get("status") == "starting" for e in events), "Missing 'starting' status"
        assert any(e.get("status") == "running" for e in events), "Missing 'running' status"
        assert any(e.get("status") in ("successful", "failed") for e in events), "Missing final status"

        # Check for EOF
        assert any(e.get("eof") for e in events), "Missing EOF marker"

        print("\n=== TEST PASSED ===")


def test_worker_info():
    """Test the --worker-info flag."""
    result = subprocess.run(
        [sys.executable, "-m", "ftl2_runner", "worker", "--worker-info"],
        capture_output=True,
        cwd=str(Path(__file__).parent.parent),
    )

    output = result.stdout.decode("utf-8")
    print(f"Worker info: {output}")

    # Should be YAML format with expected keys
    assert "cpu_count" in output
    assert "mem_in_bytes" in output
    assert "runner_version" in output
    assert "uuid" in output
    assert result.returncode == 0

    print("=== WORKER INFO TEST PASSED ===")


if __name__ == "__main__":
    print("Testing --worker-info...")
    test_worker_info()
    print()

    print("Testing streaming protocol...")
    test_worker_streaming()
