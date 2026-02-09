"""Integration test for ftl2-runner with Receptor.

This test requires the receptor binary to be available. It will be skipped
if receptor is not found.

To build receptor:
    cd /path/to/receptor
    make receptor
    cp receptor /usr/local/bin/  # or add to PATH
"""

import base64
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import pytest


def find_receptor() -> str | None:
    """Find the receptor binary."""
    # Check PATH
    receptor = shutil.which("receptor")
    if receptor:
        return receptor

    # Check common locations
    locations = [
        Path.home() / "git" / "receptor" / "receptor",
        Path("/Users/ben/git/receptor/receptor"),
        Path("/usr/local/bin/receptor"),
        Path("/opt/receptor/bin/receptor"),
    ]
    for loc in locations:
        if loc.exists() and os.access(loc, os.X_OK):
            return str(loc)

    return None


def find_receptorctl() -> str | None:
    """Find receptorctl."""
    return shutil.which("receptorctl")


def wait_for_socket(socket_path: str, timeout: float = 10.0) -> bool:
    """Wait for a Unix socket to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(socket_path):
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(socket_path)
                sock.close()
                return True
            except (ConnectionRefusedError, FileNotFoundError):
                pass
        time.sleep(0.1)
    return False


def create_private_data_dir(base_dir: Path) -> None:
    """Create a mock private_data_dir structure."""
    (base_dir / "inventory").mkdir(parents=True)
    (base_dir / "env").mkdir(parents=True)
    (base_dir / "artifacts").mkdir(parents=True)

    (base_dir / "inventory" / "hosts").write_text(
        "[all]\nlocalhost ansible_connection=local\n"
    )
    (base_dir / "env" / "extravars").write_text(
        json.dumps({"test_var": "receptor_integration", "automated": True})
    )


def create_streaming_payload(source_dir: Path, kwargs: dict) -> bytes:
    """Create the streaming input for ansible-runner worker protocol."""
    output = io.BytesIO()

    # 1. kwargs
    output.write(json.dumps({"kwargs": kwargs}).encode() + b"\n")

    # 2. zip
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for f in files:
                p = Path(root) / f
                zf.write(p, p.relative_to(source_dir))

    zip_data = zip_buf.getvalue()
    output.write(json.dumps({"zipfile": len(zip_data)}).encode() + b"\n")
    output.write(base64.b64encode(zip_data) + b"\n")

    # 3. eof
    output.write(json.dumps({"eof": True}).encode() + b"\n")

    return output.getvalue()


def parse_output(output: str) -> list[dict]:
    """Parse JSON lines from output."""
    events = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # Skip non-JSON lines (base64 data)
    return events


@pytest.fixture
def receptor_binary():
    """Get receptor binary path or skip test."""
    receptor = find_receptor()
    if not receptor:
        pytest.skip("receptor binary not found - install or build receptor first")
    return receptor


@pytest.fixture
def receptorctl_binary():
    """Get receptorctl binary path or skip test."""
    receptorctl = find_receptorctl()
    if not receptorctl:
        pytest.skip("receptorctl not found - run: pip install receptorctl")
    return receptorctl


@pytest.fixture
def test_environment(tmp_path):
    """Set up the complete test environment."""
    # Use /tmp for socket to avoid path length limits (104 chars on macOS)
    import uuid
    short_id = str(uuid.uuid4())[:8]
    socket_path = Path(f"/tmp/receptor-{short_id}.sock")

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Get the ftl2-runner source path
    src_path = Path(__file__).parent.parent / "src"

    # Get the venv python
    venv_python = Path(sys.executable)

    # Create FTL2 test script
    ftl2_script = tmp_path / "ftl2_script.py"
    ftl2_script.write_text('''
"""Test FTL2 script for receptor integration test."""

async def run(inventory_path, extravars, on_event):
    on_event({
        "event": "module_start",
        "module": "integration_test",
        "host": "localhost",
    })
    on_event({
        "event": "module_complete",
        "module": "integration_test",
        "host": "localhost",
        "success": True,
        "changed": False,
        "result": {
            "msg": f"Integration test passed! extravars={extravars}",
            "inventory_path": inventory_path,
        },
    })
    return 0
''')

    # Create worker wrapper script
    worker_script = tmp_path / "run_worker.sh"
    worker_script.write_text(f'''#!/bin/bash
export PYTHONPATH="{src_path}"
"{venv_python}" -c "
import sys
from ftl2_runner.worker import run_worker
sys.exit(run_worker(
    '{work_dir}',
    0,
    '{ftl2_script}'
))
"
''')
    worker_script.chmod(0o755)

    # Create receptor config
    receptor_config = tmp_path / "receptor.yaml"
    receptor_config.write_text(f'''---
- node:
    id: test-node

- log-level:
    level: error

- tcp-listener:
    port: 0

- control-service:
    service: control
    filename: {socket_path}

- work-command:
    worktype: ansible-runner
    command: {worker_script}
    allowruntimeparams: false
''')

    # Create source private_data_dir for payload
    source_dir = tmp_path / "source"
    create_private_data_dir(source_dir)

    return {
        "tmp_path": tmp_path,
        "socket_path": str(socket_path),
        "work_dir": work_dir,
        "receptor_config": receptor_config,
        "source_dir": source_dir,
    }


def test_receptor_integration(receptor_binary, receptorctl_binary, test_environment):
    """Test ftl2-runner with receptor end-to-end."""
    env = test_environment
    receptor_proc = None

    try:
        # Start receptor
        receptor_proc = subprocess.Popen(
            [receptor_binary, "-c", str(env["receptor_config"])],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for socket
        if not wait_for_socket(env["socket_path"], timeout=10.0):
            stdout, stderr = receptor_proc.communicate(timeout=1)
            pytest.fail(
                f"Receptor failed to start.\n"
                f"stdout: {stdout.decode()}\n"
                f"stderr: {stderr.decode()}"
            )

        # Create payload
        payload = create_streaming_payload(
            env["source_dir"],
            {"ident": "integration-test-001"},
        )
        payload_file = env["tmp_path"] / "payload.bin"
        payload_file.write_bytes(payload)

        # Submit work
        result = subprocess.run(
            [
                receptorctl_binary,
                "--socket", env["socket_path"],
                "work", "submit", "ansible-runner",
                "--node", "test-node",
                "--payload", str(payload_file),
                "--follow",
            ],
            capture_output=True,
            timeout=30,
        )

        output = result.stdout.decode()
        stderr = result.stderr.decode()

        # Parse output
        events = parse_output(output)

        # Debug output on failure
        if result.returncode != 0 or not events:
            print(f"Return code: {result.returncode}")
            print(f"stdout: {output}")
            print(f"stderr: {stderr}")

        # Verify expected events
        statuses = [e.get("status") for e in events if "status" in e]
        event_types = [e.get("event") for e in events if "event" in e]

        assert "starting" in statuses, f"Missing 'starting' status. Events: {events}"
        assert "running" in statuses, f"Missing 'running' status. Events: {events}"
        assert "successful" in statuses, f"Missing 'successful' status. Events: {events}"

        assert "runner_on_start" in event_types, f"Missing runner_on_start. Events: {events}"
        assert "runner_on_ok" in event_types, f"Missing runner_on_ok. Events: {events}"
        assert "playbook_on_stats" in event_types, f"Missing playbook_on_stats. Events: {events}"

        # Verify EOF
        assert any(e.get("eof") for e in events), f"Missing EOF marker. Events: {events}"

        # Verify the result message
        ok_events = [e for e in events if e.get("event") == "runner_on_ok"]
        assert len(ok_events) == 1
        result_msg = ok_events[0]["event_data"]["res"]["msg"]
        assert "Integration test passed!" in result_msg
        assert "receptor_integration" in result_msg

    finally:
        # Cleanup receptor
        if receptor_proc:
            receptor_proc.send_signal(signal.SIGTERM)
            try:
                receptor_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                receptor_proc.kill()
        # Cleanup socket
        socket_file = Path(env["socket_path"])
        if socket_file.exists():
            socket_file.unlink()


def test_receptor_worker_info(receptor_binary, receptorctl_binary, test_environment):
    """Test that --worker-info works through receptor."""
    env = test_environment

    # Modify config to use --worker-info
    venv_python = Path(sys.executable)
    src_path = Path(__file__).parent.parent / "src"

    worker_info_script = env["tmp_path"] / "worker_info.sh"
    worker_info_script.write_text(f'''#!/bin/bash
export PYTHONPATH="{src_path}"
"{venv_python}" -m ftl2_runner worker --worker-info
''')
    worker_info_script.chmod(0o755)

    # Use short path for socket (Unix socket path limit)
    import uuid
    short_id = str(uuid.uuid4())[:8]
    socket_path = Path(f"/tmp/receptor-info-{short_id}.sock")

    receptor_config = env["tmp_path"] / "receptor_info.yaml"
    receptor_config.write_text(f'''---
- node:
    id: info-node

- log-level:
    level: error

- tcp-listener:
    port: 0

- control-service:
    service: control
    filename: {socket_path}

- work-command:
    worktype: worker-info
    command: {worker_info_script}
    allowruntimeparams: false
''')

    receptor_proc = None
    try:
        receptor_proc = subprocess.Popen(
            [receptor_binary, "-c", str(receptor_config)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if not wait_for_socket(str(socket_path), timeout=10.0):
            stdout, stderr = receptor_proc.communicate(timeout=1)
            pytest.fail(
                f"Receptor failed to start for worker-info test.\n"
                f"stdout: {stdout.decode()}\n"
                f"stderr: {stderr.decode()}"
            )

        result = subprocess.run(
            [
                receptorctl_binary,
                "--socket", str(socket_path),
                "work", "submit", "worker-info",
                "--node", "info-node",
                "--no-payload",
                "--follow",
            ],
            capture_output=True,
            timeout=10,
        )

        output = result.stdout.decode()

        # Should contain YAML with worker info
        assert "cpu_count" in output, f"Missing cpu_count in output: {output}"
        assert "mem_in_bytes" in output, f"Missing mem_in_bytes in output: {output}"
        assert "runner_version" in output, f"Missing runner_version in output: {output}"

    finally:
        if receptor_proc:
            receptor_proc.send_signal(signal.SIGTERM)
            try:
                receptor_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                receptor_proc.kill()
        # Cleanup socket
        if socket_path.exists():
            socket_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
