"""Wire protocol **version 2** (spec §3, §6.6).

Version 2 extends the v1 display contract with one optional field (spec §3.1):

- ``tags`` — free-form labels shown as chips on the dashboard, carried as a list
  (possibly empty).

Everything else is identical to v1. Like every version this module is
self-contained: it is registered in :mod:`webprogress_python.protocol` and the
``/version`` switch picks it whenever a server advertises protocol 2.
"""

from __future__ import annotations

from ..contract import (
    DEFAULT_COLOUR,
    DEFAULT_INITIAL,
    DEFAULT_RATE,
    ProgressUpdate,
)
from .base import Protocol, ReportSnapshot


class ProtocolV2(Protocol):
    """Protocol v2: the v1 contract plus ``tags``."""

    version = 2
    ingest_path = "/handler"

    def build_payload(self, snapshot: ReportSnapshot) -> dict:
        """Build a v2 payload, applying the §4.3 fallback defaults.

        The v2 field is always emitted: ``tags`` as a list (empty when the task
        has none).
        """
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
            # v2 addition (spec §3.1): always present on the wire.
            tags=list(snapshot.tags or []),
        ).to_payload()
