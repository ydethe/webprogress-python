"""Protocol selection — the version switch (spec §6.6, architecture §2).

This package holds one module per wire-protocol version (:mod:`.v1`, and a
future :mod:`.v2` beside it) plus the switch that chooses between them from the
server's advertised ``/version``. Adding a new version is a two-line change
here — import the class and register it in ``_PROTOCOLS`` — and nothing else in
the reporter needs to know which version it is talking.

The handshake is best-effort and advisory: it never raises and never blocks the
tracked task. If the server is unreachable or silent (it never advertises a
usable version), selection falls back to the default protocol and reporting
continues. If instead the server *does* advertise a concrete version that this
client does not implement, the client cannot safely speak it: negotiation warns
and selects a sentinel that disables reporting for the session.
"""

from __future__ import annotations

import warnings
from typing import Optional, Union

import requests

from .base import Protocol, ReportSnapshot
from .v1 import ProtocolV1
from .v2 import ProtocolV2
from .v3 import ProtocolV3

# The server's version-handshake endpoint (spec §8).
_VERSION_PATH = "/version"

# Registry of implemented wire-protocol versions. Adding a version is a two-line
# change: import its class and register it here; the switch below then selects
# it automatically whenever a server advertises that version.
_PROTOCOLS: dict[int, type[Protocol]] = {
    1: ProtocolV1,
    2: ProtocolV2,
    3: ProtocolV3,
}

# Version spoken when no handshake has happened (or it failed): a standalone bar,
# an unreachable server, or a server advertising a version we don't implement.
# We deliberately default to the v1 subset — the safe fields every server
# understands — and let a successful handshake (§6.6) upgrade to a richer
# version. A reporter only emits the optional v2 fields once a server has
# advertised that it speaks them.
DEFAULT_PROTOCOL_VERSION = 1

__all__ = [
    "DEFAULT_PROTOCOL_VERSION",
    "Protocol",
    "ProtocolV1",
    "ProtocolV2",
    "ProtocolV3",
    "ReportSnapshot",
    "UnsupportedProtocolWarning",
    "default_protocol",
    "negotiate",
]


class UnsupportedProtocolWarning(UserWarning):
    """Warned when a server advertises a protocol version this client can't speak."""


class _UnsupportedProtocol(Protocol):
    """Sentinel for a server version this client cannot speak: reporting is off.

    Selected by :func:`negotiate` when the server advertises a concrete protocol
    version absent from ``_PROTOCOLS``. It carries the advertised ``version`` for
    display but marks itself unsupported, so the reporter sends nothing under it.
    """

    supported = False
    ingest_path = ""

    def __init__(self, version: int):
        self.version = version

    def build_payload(self, snapshot: ReportSnapshot) -> dict:
        # Never reached — the reporter checks ``supported`` before building — but
        # a protocol must never raise (see base), so return an empty payload.
        return {}


def _instantiate(version: int) -> Protocol:
    cls = _PROTOCOLS.get(version, _PROTOCOLS[DEFAULT_PROTOCOL_VERSION])
    return cls()


def default_protocol() -> Protocol:
    """The protocol used without (or before) a successful handshake."""
    return _instantiate(DEFAULT_PROTOCOL_VERSION)


def _extract_version(doc: object) -> Optional[int]:
    """Pull the protocol version out of a ``/version`` document, tolerantly."""
    if not isinstance(doc, dict):
        return None
    for field in ("protocol", "protocol_version", "protocolVersion"):
        if field in doc:
            try:
                return int(doc[field])
            except (TypeError, ValueError):
                return None
    return None


def negotiate(
    host: str,
    session: Optional[requests.Session] = None,
    timeout: Union[float, tuple] = (1.0, 1.0),
) -> Protocol:
    """Perform the §6.6 handshake and return the protocol to use.

    Best-effort on *transport*: if the server can't be reached or never advertises
    a usable version (no host, unreachable, bad response, missing field), this
    returns :func:`default_protocol` so the caller keeps reporting.

    If the server *does* advertise a concrete version this client does not
    implement, that is different from silence: the client cannot safely shape a
    message for it. It then emits an :class:`UnsupportedProtocolWarning` and
    returns an unsupported-protocol sentinel, under which the reporter sends
    nothing.
    """
    if not host:
        return default_protocol()
    http = session or requests
    try:
        resp = http.get(host + _VERSION_PATH, timeout=timeout)
        version = _extract_version(resp.json())
    except Exception:
        # Unreachable, timed out, non-JSON, etc. — advisory step, so ignore.
        return default_protocol()
    if version is None:
        # Server answered but advertised no usable version — keep reporting.
        return default_protocol()
    if version not in _PROTOCOLS:
        warnings.warn(
            f"webprogress server advertises protocol version {version}, which this "
            f"client does not support (supported versions: {sorted(_PROTOCOLS)}); "
            f"reporting is disabled for this session.",
            UnsupportedProtocolWarning,
            stacklevel=2,
        )
        return _UnsupportedProtocol(version)
    return _instantiate(version)
