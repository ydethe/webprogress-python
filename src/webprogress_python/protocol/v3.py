"""Wire protocol **version 3** (spec §3, §6.6).

Version 3 extends the v2 display contract with one field (spec §3.1):

- ``uuid`` — the reporter-assigned identity of this particular **run** of the
  task (one value per run, §6.3). The server draws one dashboard card per uuid,
  so a restarted task that mints a new uuid opens a fresh card instead of
  reviving the previous run's. A pre-v3 reporter omits the field and the server
  falls back to the ``(script, user_hostname, description)`` triple, which
  cannot tell successive runs apart.

Everything else is identical to v2 (the ``tags`` field included). Like every
version this module is self-contained: it is registered in
:mod:`webprogress_python.protocol` and the ``/version`` switch picks it whenever
a server advertises protocol 3.
"""

from __future__ import annotations

from ..contract import (
    DEFAULT_COLOUR,
    DEFAULT_INITIAL,
    DEFAULT_RATE,
    ProgressUpdate,
)
from .base import Protocol, ReportSnapshot


class ProtocolV3(Protocol):
    """Protocol v3: the v2 contract plus the per-run ``uuid``."""

    version = 3
    ingest_path = "/handler"

    def build_payload(self, snapshot: ReportSnapshot) -> dict:
        """Build a v3 payload, applying the §4.3 fallback defaults.

        The fields added since v1 are always emitted: ``tags`` as a list (empty
        when the task has none) and ``uuid`` as the reporter-assigned per-run
        identity.
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
            # v3 addition (spec §3.1): the per-run identity, always present.
            uuid=snapshot.uuid,
        ).to_payload()
