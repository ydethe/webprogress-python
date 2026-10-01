"""The protocol-version interface (spec §6.6, architecture §2).

A *protocol* is one concrete version of the wire contract (spec §3): it knows
which fields to put on the wire and where to send them. Each version lives in
its own module (``v1`` today, a future ``v2`` alongside it) and implements this
interface; the :mod:`webprogress_python.protocol` switch selects one per the
server's advertised ``/version`` (§6.6).

Because reporting is best-effort, a protocol must never raise while building a
payload — it maps whatever state it is given to the shape its version speaks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass
class ReportSnapshot:
    """A version-neutral snapshot of reporter state for one tick.

    This is the raw material every protocol receives; each version decides which
    of these to emit, in what shape, and which defaults to apply. ``format_dict``
    is tqdm's own progress snapshot (``n``, ``total``, ``elapsed``, ``rate``, …).

    ``tags`` was added with protocol v2 (spec §3.1) and ``uuid`` with protocol v3
    (the reporter-assigned per-run identity, §3.1/§6.3); older protocols simply
    ignore the fields their version does not speak.
    """

    user_hostname: str
    user_login: str
    script: str
    description: str
    colour: str | None
    key: str
    format_dict: Mapping
    tags: list[str] = field(default_factory=list)
    uuid: str = ""


class Protocol(ABC):
    """One version of the reporter↔server wire contract."""

    #: Wire-protocol version number this implementation speaks (spec §6.6).
    version: int

    #: Server path that ingests one update for this version (spec §8).
    ingest_path: str

    #: Whether the reporter may send under this protocol. A real version sets it
    #: True; the sentinel used when a server advertises a version this client
    #: cannot speak sets it False, which disables reporting (see the negotiation
    #: switch in :mod:`webprogress_python.protocol`).
    supported: bool = True

    @abstractmethod
    def build_payload(self, snapshot: ReportSnapshot) -> dict:
        """Serialize a snapshot into this version's JSON-ready wire payload."""
        raise NotImplementedError
