# Proposal: Move Event Streaming to FTL2 Core

## Summary

Move the ansible-runner event translation from ftl2-runner scripts into FTL2 core, so scripts don't need to manually emit events. FTL2's automation context already tracks module execution internally - it should expose this in a format compatible with ansible-runner.

## Current State

Scripts must manually emit events:

```python
async def run(inventory_path, extravars, on_event):
    on_event({"event": "module_start", "module": "ping", "host": "localhost"})

    async with automation() as ftl:
        result = await ftl.ping()

    on_event({"event": "module_complete", "module": "ping", "host": "localhost",
              "success": True, "result": result})
    return 0
```

**Problems:**
1. Boilerplate - every module call needs manual event emission
2. Error-prone - easy to forget events or emit incorrect data
3. Duplicated logic - FTL2 already tracks this internally
4. Inconsistent - script authors may emit different event formats

## Proposed State

FTL2 automation context handles event emission automatically:

```python
async def run(inventory_path, extravars, context):
    async with context.automation() as ftl:
        await ftl.ping()
        await ftl.file(path="/tmp/test", state="directory")
    return 0
```

Events are emitted automatically when modules execute. The script author focuses on automation logic, not event plumbing.

## Requirements

### 1. Event Format

FTL2 must emit events compatible with ansible-runner's expected format:

```python
# Module starting
{
    "uuid": "<uuid4>",
    "counter": 1,
    "created": "2026-02-09T12:00:00.000000+00:00",
    "runner_ident": "<job_id>",
    "event": "runner_on_start",
    "event_data": {
        "host": "localhost",
        "task": "ping",
        "task_action": "ping",
    }
}

# Module succeeded
{
    "uuid": "<uuid4>",
    "counter": 2,
    "created": "2026-02-09T12:00:00.100000+00:00",
    "runner_ident": "<job_id>",
    "event": "runner_on_ok",
    "event_data": {
        "host": "localhost",
        "task": "ping",
        "task_action": "ping",
        "res": {"ping": "pong"},
        "changed": false,
        "duration": 0.05,
    }
}

# Module failed
{
    "event": "runner_on_failed",
    "event_data": {
        "host": "localhost",
        "task": "command",
        "res": {"msg": "Error message", "rc": 1},
        "changed": false,
    }
}

# Playbook stats (end of run)
{
    "event": "playbook_on_stats",
    "event_data": {
        "stats": {
            "localhost": {"ok": 5, "changed": 2, "failed": 0, "skipped": 0}
        }
    }
}
```

### 2. Event Types Mapping

| FTL2 Internal Event | ansible-runner Event |
|---------------------|---------------------|
| Module execution start | `runner_on_start` |
| Module success | `runner_on_ok` |
| Module failure | `runner_on_failed` |
| Module skipped | `runner_on_skipped` |
| Host unreachable | `runner_on_unreachable` |
| Automation complete | `playbook_on_stats` |

### 3. Required Event Data

Each event must include:

| Field | Description | Source |
|-------|-------------|--------|
| `uuid` | Unique event ID | Generated |
| `counter` | Sequential event number | Auto-increment |
| `created` | ISO 8601 timestamp | `datetime.now(timezone.utc)` |
| `runner_ident` | Job identifier | From context config |
| `event` | Event type | Mapped from FTL2 event |
| `event_data.host` | Target host | From module execution |
| `event_data.task` | Module name | From module call |
| `event_data.res` | Module result | From module return |
| `event_data.changed` | Whether state changed | From module return |
| `event_data.duration` | Execution time (seconds) | Measured |

### 4. Streaming Interface

FTL2 needs to support streaming events to a callback or file descriptor:

```python
# Option A: Callback-based (current pattern)
async with automation(on_event=my_callback) as ftl:
    await ftl.ping()

# Option B: Context manager with runner protocol
async with automation.for_runner(ident="job-123", stream=sys.stdout) as ftl:
    await ftl.ping()

# Option C: Event format selection
async with automation(
    on_event=my_callback,
    event_format="ansible-runner",  # or "ftl2" (default)
) as ftl:
    await ftl.ping()
```

### 5. Stats Tracking

FTL2 must track per-host statistics:

```python
{
    "hostname": {
        "ok": 0,       # Successful module runs
        "changed": 0,  # Modules that made changes
        "failed": 0,   # Failed module runs
        "skipped": 0,  # Skipped modules (check_mode, conditions)
        "unreachable": 0,  # Host connection failures
    }
}
```

These are emitted as `playbook_on_stats` when the automation context exits.

## Proposed Interface

### Option 1: Runner Context Factory

Add a factory method specifically for ansible-runner integration:

```python
# In FTL2 core
class AutomationContext:
    @classmethod
    def for_runner(
        cls,
        ident: str,
        stream: BinaryIO,
        inventory: str | dict | None = None,
        **kwargs,
    ) -> "AutomationContext":
        """Create context configured for ansible-runner event streaming."""

        translator = AnsibleRunnerEventTranslator(ident, stream)
        return cls(
            inventory=inventory,
            on_event=translator,
            **kwargs,
        )
```

Usage in ftl2-runner:

```python
async def run(inventory_path, extravars, runner_context):
    async with runner_context.automation() as ftl:
        await ftl.ping()
    return 0
```

### Option 2: Event Format Parameter

Add event format selection to existing interface:

```python
async with automation(
    on_event=stream_callback,
    event_format="ansible-runner",
    runner_ident="job-123",
) as ftl:
    await ftl.ping()
```

### Option 3: Separate Translator Module

Keep translation in ftl2-runner but make it wrap the automation context:

```python
# In ftl2-runner
class RunnerAutomation:
    def __init__(self, ident: str, stream: BinaryIO, **kwargs):
        self.translator = EventTranslator(ident, stream)
        self.kwargs = kwargs

    @asynccontextmanager
    async def automation(self):
        async with ftl2_automation(on_event=self.translator, **self.kwargs) as ftl:
            yield ftl
        self.translator.emit_stats(ftl.stats)
```

Usage:

```python
async def run(inventory_path, extravars, runner):
    async with runner.automation() as ftl:
        await ftl.ping()
    return 0
```

## Recommended Approach

**Option 3** (Separate Translator Module) is recommended because:

1. **No FTL2 core changes required** - Can ship immediately
2. **Clean separation** - ansible-runner format is AWX-specific, not core FTL2
3. **Flexibility** - Easy to support other event formats later
4. **Testability** - Translator can be tested independently

The script interface becomes:

```python
# Before (manual events)
async def run(inventory_path, extravars, on_event):
    on_event({"event": "module_start", ...})
    async with automation() as ftl:
        result = await ftl.ping()
    on_event({"event": "module_complete", ...})
    return 0

# After (automatic events)
async def run(inventory_path, extravars, runner):
    async with runner.automation(inventory=inventory_path) as ftl:
        await ftl.ping()
    return 0
```

## Implementation Plan

### Phase 1: ftl2-runner Changes

1. Create `RunnerContext` class that wraps FTL2 automation
2. Update worker to pass `RunnerContext` instead of `on_event` callback
3. Update script interface signature
4. Migrate examples to new interface

### Phase 2: FTL2 Core Enhancements (Optional)

If needed for performance or functionality:

1. Add `stats` property to AutomationContext tracking per-host results
2. Ensure all module executions emit consistent internal events
3. Add `event_format` parameter for built-in translation

### Phase 3: Documentation

1. Update ftl2-runner README and examples
2. Document script interface contract
3. Add migration guide for existing scripts

## Script Interface Contract

### Current (v0.1)

```python
async def run(
    inventory_path: str | None,
    extravars: dict,
    on_event: Callable[[dict], None],
) -> int:
    """
    Args:
        inventory_path: Path to inventory directory
        extravars: Extra variables from AWX
        on_event: Callback for FTL2-format events (manual emission required)

    Returns:
        Exit code (0 = success)
    """
```

### Proposed (v0.2)

```python
async def run(
    inventory_path: str | None,
    extravars: dict,
    runner: RunnerContext,
) -> int:
    """
    Args:
        inventory_path: Path to inventory directory
        extravars: Extra variables from AWX
        runner: Context for creating automation with automatic event streaming

    Returns:
        Exit code (0 = success)
    """
```

## Migration

Scripts can be migrated incrementally:

```python
# Detect interface version
async def run(inventory_path, extravars, context):
    if callable(context):
        # Old interface: context is on_event callback
        return await run_v1(inventory_path, extravars, context)
    else:
        # New interface: context is RunnerContext
        return await run_v2(inventory_path, extravars, context)
```

## Open Questions

1. **Should FTL2 core know about ansible-runner format?**
   - Pro: Single source of truth
   - Con: Couples FTL2 to AWX-specific format

2. **How to handle custom events from scripts?**
   - Allow `runner.emit_event()` for script-specific events?
   - Or restrict to only module execution events?

3. **Should we support check_mode / dry-run through the runner interface?**
   - AWX passes this as part of job parameters
   - FTL2 automation already supports `check_mode=True`

4. **How to handle long-running operations with keepalive?**
   - ansible-runner has `keepalive_seconds` for periodic status events
   - Should FTL2 emit these automatically during long module runs?
