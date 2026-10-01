"""The shared update contract (specification §3, architecture §2).

This is the single message definition shared by reporter and server. The
reporter serializes exactly these fields; the server validates incoming
messages against exactly these fields. Any change here is a contract change
that touches both sides at once.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Fallback defaults applied when a value is not yet available (spec §4.3).
DEFAULT_RATE = 0.0
DEFAULT_INITIAL = 0
DEFAULT_COLOUR = "#0000ff"  # standard blue


@dataclass
class ProgressUpdate:
    """One progress update message — the wire payload.

    Display fields (§3.1) are shown to the user; ``user_src_address`` (§3.2) is
    routing metadata the reporter leaves empty for the server to stamp; ``key``
    (§3.3) is the credential and is not a display field.
    """

    # --- Display fields (§3.1) ---
    user_hostname: str
    user_login: str
    progress: int
    total: Optional[int]
    description: str
    elapsed: float
    unit: str
    unit_scale: Any
    rate: float
    unit_divisor: int
    initial: int
    colour: str

    # --- Credential (§3.3) ---
    key: str

    # --- Routing / metadata (§3.2) ---
    # The reporter always leaves this empty; the server fills it from the
    # received request and it is authoritative only when set by the server.
    user_src_address: str = field(default="")

    def to_payload(self) -> dict:
        """Serialize to the JSON-ready dict sent to the server."""
        return asdict(self)
