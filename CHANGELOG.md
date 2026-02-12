# Changelog

All notable changes to ftl2-runner are documented in this file.

## [0.5.0] - 2026-02-12

### Added
- ANSI event encoding for AWX container mode, matching ansible-runner's `awx_display` callback plugin format
- Event hierarchy: `playbook_on_start`, `playbook_on_play_start`, `playbook_on_task_start` events with `parent_uuid` chain
- `stdout`, `start_line`, `end_line` fields on all events for AWX job output reconstruction
- AWX-compatible `playbook_on_stats` event with transposed per-status format (`ok`, `changed`, `failures`, `dark`, `skipped`)
- Colored output matching Ansible defaults: green for ok, yellow for changed, red for failed
- Concise task output at default verbosity (hide result JSON, matching Ansible behavior)
- `RunnerContext.has_failures()` method to check for failed tasks

### Changed
- Job exit code is now 2 when tasks fail but script returns 0, matching Ansible convention
- FTL2's own SUMMARY output suppressed in favor of PLAY RECAP event (`quiet=True`)

## [0.4.0] - 2026-02-11

### Added
- Playbook-as-script support: AWX playbook files are executed as FTL2 Python scripts
- `playbook` subcommand (`ftl2-runner playbook`) providing ansible-playbook CLI compatibility for container mode
- `hosts: all` trick for `.yml` files that pass AWX's playbook discovery regex while being valid Python
- Worker mode now extracts `playbook` from kwargs and uses it as the script path
- `SourceFileLoader` for loading scripts with any file extension (including `.yml`)
- Dev Containerfile (`ee/Containerfile.dev`) for building EEs from local source
- `ansible-playbook` wrapper script in EE that routes to `ftl2-runner playbook`
- Example playbook script (`examples/ping_playbook.yml`)

## [0.3.1] - 2026-02-11

### Added
- `--extra-vars` (`-e`) and `--ask-pass` / `--ask-become-pass` arguments to adhoc command for ansible CLI compatibility

## [0.3.0] - 2026-02-11

### Added
- `adhoc` subcommand for running ad-hoc modules, similar to the `ansible` CLI
- Support for key=value, JSON, and free-form module argument formats
- Ansible-compatible CLI flags (`-m`, `-a`, `-i`, `-C`, `-v`, `-u`, `-b`, `-f`, `--diff`)
- Execution environment (`ee/`) with Containerfile and ansible-builder config for AWX deployment
- Symlink from `ansible-runner` to `ftl2-runner` in EE
- Wrapper script for `ansible` CLI that calls `ftl2-runner adhoc`

## [0.2.0] - 2026-02-09

### Added
- `RunnerContext` class for automatic event streaming from FTL2 modules
- `runner.automation()` context manager that wraps FTL2's automation context
- `runner.emit_event()` for custom (non-module) events
- Automatic stats tracking for `playbook_on_stats` event
- Design proposal for moving event streaming to FTL2 core (`docs/proposal-ftl2-event-streaming.md`)
- Example FTL2 scripts (`examples/`)

### Changed
- FTL2 script interface now receives a `runner` (RunnerContext) instead of raw `on_event` callback
- Scripts use `async with runner.automation() as ftl:` instead of manually calling `automation()`

## [0.1.0] - 2026-02-09

### Added
- Initial implementation of ftl2-runner worker CLI
- Streaming protocol for stdin/stdout communication with Receptor
- Event translation from FTL2 format to ansible-runner format (`module_start` -> `runner_on_start`, etc.)
- Artifact file management (job_events, stdout, stderr, rc, status)
- `--worker-info` endpoint returning CPU, memory, and version info
- `worker cleanup` stub subcommand
- Unit tests for streaming protocol
- Automated Receptor integration tests
- Design documentation with architecture diagrams
- Receptor testing guide
