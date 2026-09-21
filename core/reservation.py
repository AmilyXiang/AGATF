"""Resource reservation for Unified Execution Flow step 7 (Reserve) and step 10 (Release).

Pre-check only checks whether a resource exists; Reserve actually locks it so
two concurrent plans cannot use the same shared DUT or bench resource (Robot /
Camera / Audio / Power). Reserve (step 7) and Release (step 10) are paired:
lock before Execute, release after Cleanup.

This PoC manager is an in-memory lock set. A real deployment would back this
with a shared lock service (P1 Resource reservation).
"""
from __future__ import annotations

from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class ReservationError(RuntimeError):
    """Raised when a requested resource is already reserved by someone else."""


class ResourceManager:
    """Tracks which resource ids are currently locked."""

    def __init__(self) -> None:
        self._locked: set[str] = set()

    def reserve(self, resource_ids: list[str]) -> None:
        # Step 7: refuse the whole request if any resource is already taken.
        conflicts = self._locked.intersection(resource_ids)
        if conflicts:
            logger.error("reserve conflict: %s already locked", sorted(conflicts))
            raise ReservationError(f"resources already reserved: {sorted(conflicts)}")
        self._locked.update(resource_ids)
        logger.debug("reserved %s (locked now: %s)", resource_ids, sorted(self._locked))

    def release(self, resource_ids: list[str]) -> None:
        # Step 10: return the resources so later cases/plans can use them.
        self._locked.difference_update(resource_ids)
        logger.debug("released %s (locked now: %s)", resource_ids, sorted(self._locked))

    @property
    def locked(self) -> set[str]:
        return set(self._locked)

    @contextmanager
    def reserved(self, resource_ids: list[str]):
        """Reserve for the duration of a block, always releasing on exit."""
        self.reserve(resource_ids)
        try:
            yield
        finally:
            self.release(resource_ids)
