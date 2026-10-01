"""Wire protocol **version 1** (spec §3, §6.6).

This is the current protocol: the full display contract including the ``script``
field. It is self-contained in this module so that a future protocol v2 is just
a sibling ``v2.py`` registered in :mod:`webprogress_python.protocol` — no edits
to this file, and the ``/version`` switch picks between them at runtime.
"""

from __future__ import annotations

from ..contract import (
    DEFAULT_COLOUR,
    DEFAULT_INITIAL,
    DEFAULT_RATE,
    ProgressUpdate,
)
from .base import Protocol, ReportSnapshot


class ProtocolV1(Protocol):
    """Protocol v1: the current contract, ``script`` included."""

    version = 1
    ingest_path = "/handler"

    def build_payload(self, snapshot: ReportSnapshot) -> dict:
        """Build a v1 payload, applying the §4.3 fallback defaults."""
        d = snapshot.format_dict
        return ProgressUpdate(
            user_hostname=snapshot.user_hostname,
            user_login=snapshot.user_login,
            script=snapshot.script,
            progress=d.get("n"),
            total=d.get("total"),
            description=snapshot.description,
            elapsed=d.get("elapsed"),
            unit=d.get("unit"),
            unit_scale=d.get("unit_scale"),
            # Fallback defaults for values not yet available (spec §4.3).
            rate=d.get("rate") or DEFAULT_RATE,
            unit_divisor=d.get("unit_divisor"),
            initial=d.get("initial") or DEFAULT_INITIAL,
            colour=snapshot.colour or DEFAULT_COLOUR,
            key=snapshot.key,
            # Reporter leaves this empty; the server stamps it (spec §3.2).
            user_src_address="",
        ).to_payload()
