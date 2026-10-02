"""Wire protocol **version 4** (spec §3, §6.6).

Version 4 extends the v3 display contract with three fields (spec §3.1):

- ``library`` — name of the reporting client library (e.g. ``"webprogress"``);
- ``library_version`` — version of that library; the two are shown together as
  the dashboard chip ``library@library_version``;
- ``criticity`` — importance of the task (``trivial`` / ``standard`` /
  ``critical``), which gates its out-of-band notifications (§6.7). An absent or
  unrecognised value is treated as ``standard``.

None of the three are part of a task's identity. Everything else is identical to
v3 (the ``tags`` and ``uuid`` fields included). Like every version this module is
self-contained: it is registered in :mod:`webprogress_python.protocol` and the
``/version`` switch picks it whenever a server advertises protocol 4.
"""

from __future__ import annotations

from ..contract import (
    DEFAULT_COLOUR,
    DEFAULT_INITIAL,
    DEFAULT_RATE,
    ProgressUpdate,
    normalize_criticity,
)
from .base import Protocol, ReportSnapshot


class ProtocolV4(Protocol):
    """Protocol v4: the v3 contract plus ``library``, ``library_version``, ``criticity``."""

    version = 4
    ingest_path = "/handler"

    def build_payload(self, snapshot: ReportSnapshot) -> dict:
        """Build a v4 payload, applying the §4.3 fallback defaults.

        The fields added since v1 are always emitted: ``tags`` as a list (empty
        when the task has none), ``uuid`` as the reporter-assigned per-run
        identity, and the v4 trio ``library`` / ``library_version`` /
        ``criticity`` (the last normalised to a valid level, defaulting to
        ``standard``).
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
            # v4 additions (spec §3.1): always present on the wire.
            library=snapshot.library,
            library_version=snapshot.library_version,
            criticity=normalize_criticity(snapshot.criticity),
        ).to_payload()
