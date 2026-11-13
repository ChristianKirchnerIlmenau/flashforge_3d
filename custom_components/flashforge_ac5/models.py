"""Shared data models for the FlashForge integration."""

from __future__ import annotations

from dataclasses import dataclass

from flashforge.models import FFMachineInfo


@dataclass(slots=True)
class PrinterSnapshot:
    """A single consistent read of the printer state.

    Every entity reads from this object so that a poll cycle produces values
    that agree with each other (progress, layer, ETA all from the same reply).
    """

    info: FFMachineInfo

    @property
    def is_active_print(self) -> bool:
        """Return True while a job is actually advancing or paused."""
        return self.info.machine_state.value in ("printing", "pausing", "paused", "heating")

    @property
    def is_paused(self) -> bool:
        """Return True when a job is paused and can be resumed."""
        return self.info.machine_state.value in ("paused", "pausing")
