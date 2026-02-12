"""Test the playbook ANSI event encoding path.

This tests the container mode path where ftl2-runner playbook encodes
events as ANSI escape sequences for AWX's OutputEventFilter to extract.
"""

import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# Regex matching OutputEventFilter's extraction pattern
EVENT_DATA_RE = re.compile(
    rb"\x1b\[K((?:[A-Za-z0-9+/=]+\x1b\[\d+D)+)\x1b\[K"
)


def decode_ansi_event(match: re.Match) -> dict:
    """Decode an ANSI-encoded event, same as OutputEventFilter."""
    raw = match.group(1)
    # Strip cursor-backward codes
    b64data = re.sub(rb"\x1b\[\d+D", b"", raw)
    return json.loads(base64.b64decode(b64data))


def extract_events(stdout: bytes) -> list[dict]:
    """Extract all ANSI-encoded events from stdout."""
    return [decode_ansi_event(m) for m in EVENT_DATA_RE.finditer(stdout)]


def create_script(path: Path, content: str) -> None:
    """Write a test script file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def run_playbook_cmd(script_path: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run ftl2-runner playbook and return the result."""
    cmd = [sys.executable, "-m", "ftl2_runner", "playbook"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(str(script_path))
    return subprocess.run(
        cmd,
        capture_output=True,
        cwd=str(Path(__file__).parent.parent),
    )


def test_playbook_ansi_encoding():
    """Test that playbook mode emits ANSI-encoded events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "test.py"
        create_script(script_path, '''
async def run(inventory_path, extravars, runner):
    async with runner.automation() as ftl:
        await ftl.ping()
    return 0
''')

        result = run_playbook_cmd(script_path)
        events = extract_events(result.stdout)

        # Should have ANSI-encoded events (begin + end markers = pairs)
        assert len(events) >= 2, f"Expected ANSI events, got {len(events)}"

        # Extract unique event types (each event appears twice: begin + end)
        event_types = list(dict.fromkeys(e.get("event") for e in events))
        assert "playbook_on_start" in event_types
        assert "playbook_on_play_start" in event_types
        assert "playbook_on_task_start" in event_types
        assert "runner_on_ok" in event_types
        assert "playbook_on_stats" in event_types

        # All events should have pid
        for e in events:
            assert "pid" in e, f"Event {e.get('event')} missing pid"

        # Check parent_uuid chain
        pb_start = next(e for e in events if e["event"] == "playbook_on_start")
        play_start = next(e for e in events if e["event"] == "playbook_on_play_start")
        task_start = next(e for e in events if e["event"] == "playbook_on_task_start")
        runner_ok = next(e for e in events if e["event"] == "runner_on_ok")

        assert play_start.get("parent_uuid") == pb_start["uuid"]
        assert task_start.get("parent_uuid") == play_start["uuid"]
        assert runner_ok.get("parent_uuid") == task_start["uuid"]

        assert result.returncode == 0


def test_playbook_ansi_visible_stdout():
    """Test that visible stdout text appears between ANSI markers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "test.py"
        create_script(script_path, '''
async def run(inventory_path, extravars, runner):
    async with runner.automation() as ftl:
        await ftl.ping()
    return 0
''')

        result = run_playbook_cmd(script_path)
        stdout = result.stdout.decode("utf-8", errors="replace")

        # Strip ANSI escape sequences to get visible text
        visible = re.sub(r"\x1b\[[^a-zA-Z]*[a-zA-Z]", "", stdout)

        assert "PLAY [FTL2 Script]" in visible
        assert "TASK [ping]" in visible
        assert "ok: [localhost]" in visible
        assert "PLAY RECAP" in visible


def test_playbook_failure_reporting():
    """Test that failed tasks produce fatal output and non-zero exit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "test.py"
        create_script(script_path, '''
async def run(inventory_path, extravars, runner):
    async with runner.automation() as ftl:
        await ftl.command(cmd="/bin/false")
    return 0
''')

        result = run_playbook_cmd(script_path)
        stdout = result.stdout.decode("utf-8", errors="replace")

        # Strip ANSI escape sequences
        visible = re.sub(r"\x1b\[[^a-zA-Z]*[a-zA-Z]", "", stdout)

        assert "fatal:" in visible
        assert "FAILED!" in visible
        assert "...ignoring" in visible
        assert "failed=1" in visible
        assert "ignored=1" in visible
        assert result.returncode == 2


def test_playbook_verbosity():
    """Test that -v shows result JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "test.py"
        create_script(script_path, '''
async def run(inventory_path, extravars, runner):
    async with runner.automation() as ftl:
        await ftl.ping()
    return 0
''')

        # Without -v: no result JSON
        result_quiet = run_playbook_cmd(script_path)
        visible_quiet = re.sub(
            r"\x1b\[[^a-zA-Z]*[a-zA-Z]", "",
            result_quiet.stdout.decode("utf-8", errors="replace"),
        )
        assert '"ping"' not in visible_quiet

        # With -v: result JSON shown
        result_verbose = run_playbook_cmd(script_path, ["-v"])
        visible_verbose = re.sub(
            r"\x1b\[[^a-zA-Z]*[a-zA-Z]", "",
            result_verbose.stdout.decode("utf-8", errors="replace"),
        )
        assert '"ping": "pong"' in visible_verbose


if __name__ == "__main__":
    print("Testing ANSI encoding...")
    test_playbook_ansi_encoding()
    print("PASSED")

    print("Testing visible stdout...")
    test_playbook_ansi_visible_stdout()
    print("PASSED")

    print("Testing failure reporting...")
    test_playbook_failure_reporting()
    print("PASSED")

    print("Testing verbosity...")
    test_playbook_verbosity()
    print("PASSED")
