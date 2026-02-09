"""RunnerContext - connects FTL2 automation to ansible-runner event streaming.

This thin wrapper passes the EventTranslator as on_event to FTL2's automation
context, so module events are automatically translated and streamed to AWX.
"""

from contextlib import asynccontextmanager
from typing import Any, BinaryIO, Callable

from ftl2 import automation

from ftl2_runner.events import EventTranslator, create_playbook_stats_event
from ftl2_runner.streaming import write_event


class RunnerContext:
    """Context for running FTL2 automation with ansible-runner event streaming.

    Instead of scripts manually emitting events:

        async def run(inventory_path, extravars, on_event):
            on_event({"event": "module_start", ...})
            async with automation() as ftl:
                result = await ftl.ping()
            on_event({"event": "module_complete", ...})
            return 0

    Scripts use RunnerContext for automatic event emission:

        async def run(inventory_path, extravars, runner):
            async with runner.automation() as ftl:
                await ftl.ping()  # Events emitted automatically
            return 0
    """

    def __init__(
        self,
        ident: str,
        on_event: Callable[[dict[str, Any]], None],
        stream: BinaryIO | None = None,
    ):
        """Initialize RunnerContext.

        Args:
            ident: Job identifier (runner_ident in events)
            on_event: Callback for translated events
            stream: Optional output stream for stats event
        """
        self.ident = ident
        self.on_event = on_event
        self.stream = stream
        self.translator = EventTranslator(ident, on_event=on_event)
        self._stats: dict[str, dict[str, int]] = {}
        self._event_counter = 0

    def _next_counter(self) -> int:
        """Get next event counter."""
        self._event_counter += 1
        return self._event_counter

    def _handle_ftl2_event(self, event: dict[str, Any]) -> None:
        """Handle event from FTL2 automation context.

        Translates FTL2 events to ansible-runner format and updates stats.
        """
        # Translate and forward the event
        self.translator(event)

        # Update stats
        if event.get("event") == "module_complete":
            host = event.get("host", "localhost")
            if host not in self._stats:
                self._stats[host] = {"ok": 0, "changed": 0, "failed": 0, "skipped": 0}

            if event.get("success"):
                self._stats[host]["ok"] += 1
                if event.get("changed"):
                    self._stats[host]["changed"] += 1
            else:
                self._stats[host]["failed"] += 1

    @asynccontextmanager
    async def automation(self, **kwargs):
        """Create FTL2 automation context with event streaming.

        Events are automatically translated to ansible-runner format.

        Args:
            **kwargs: Passed to ftl2.automation()
                - inventory: Inventory path or dict
                - check_mode: Dry-run mode
                - verbose: Verbose output
                - secrets: List of secret names to load
                - secret_bindings: Dict mapping modules to secrets

        Yields:
            FTL2 AutomationContext
        """
        async with automation(on_event=self._handle_ftl2_event, **kwargs) as ftl:
            yield ftl

    def emit_stats(self) -> None:
        """Emit playbook_on_stats event with collected statistics."""
        if self._stats:
            stats_event = create_playbook_stats_event(
                self.ident,
                self._next_counter(),
                self._stats,
            )
            self.on_event(stats_event)

    def emit_event(self, event: dict[str, Any]) -> None:
        """Emit a custom event (for script-specific progress).

        Use this for intermediate progress events that aren't module calls.

        Args:
            event: FTL2-format event dict
        """
        self.translator(event)
