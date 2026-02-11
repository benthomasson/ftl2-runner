# Changelog

All notable changes to ftl2-runner are documented in this file.

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
