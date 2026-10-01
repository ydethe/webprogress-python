"""Protocol selection — the version switch (spec §6.6, architecture §2).

This package holds one module per wire-protocol version (:mod:`.v1`, and a
future :mod:`.v2` beside it) plus the switch that chooses between them from the
server's advertised ``/version``. Adding a new version is a two-line change
here — import the class and register it in ``_PROTOCOLS`` — and nothing else in
the reporter needs to know which version it is talking.

The handshake is best-effort and advisory: it never raises and never blocks the
tracked task. If the server is unreachable, silent, or advertises a version we
do not implement, selection falls back to the default protocol.
"""

from __future__ import annotations

from typing import Optional, Union

import requests

from .base import Protocol, ReportSnapshot
from .v1 import ProtocolV1

# The server's version-handshake endpoint (spec §8).
_VERSION_PATH = "/version"

# Registry of implemented wire-protocol versions. To add protocol v2, drop a
# ``v2.py`` next to this file and register it here:
#
#     from .v2 import ProtocolV2
#     _PROTOCOLS[2] = ProtocolV2
#
# The switch below then selects v2 automatically whenever a server advertises it.
_PROTOCOLS: dict[int, type[Protocol]] = {
    1: ProtocolV1,
}

# Version used when the server can't be reached or advertises something we don't
# implement. We speak the current protocol by default.
DEFAULT_PROTOCOL_VERSION = 1

__all__ = [
    "Protocol",
    "ReportSnapshot",
    "ProtocolV1",
    "negotiate",
    "default_protocol",
    "DEFAULT_PROTOCOL_VERSION",
]


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

    Best-effort: on any failure (no host, unreachable, bad response, unknown
    version) this returns :func:`default_protocol` rather than raising, so a
    caller can always report against *some* protocol.
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
        return default_protocol()
    return _instantiate(version)
