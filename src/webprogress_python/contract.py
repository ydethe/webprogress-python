"""The shared update contract (specification §3, architecture §2).

This is the single message definition shared by reporter and server. The
reporter serializes exactly these fields; the server validates incoming
messages against exactly these fields. Any change here is a contract change
that touches both sides at once.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

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
    # Script the task belongs to; groups tasks on the dashboard and is part of a
    # task's identity (§6.3). May be empty ("unscripted"). Added at protocol v1.
    script: str
    progress: int
    total: int | None
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

    # --- Display fields added at protocol v2 (§3.1) ---
    # Free-form labels shown as chips on the dashboard; not part of a task's
    # identity. A pre-v2 reporter omits the field entirely (see ``to_payload``).
    tags: list[str] | None = None

    # --- Display fields added at protocol v3 (§3.1) ---
    # Reporter-assigned identity of this particular run of the task (one value
    # per run, §6.3): the server draws one dashboard card per uuid, so a
    # restarted task sending a new uuid opens a fresh card. A pre-v3 reporter
    # omits the field entirely (see ``to_payload``).
    uuid: str | None = None

    def to_payload(self) -> dict:
        """Serialize to the JSON-ready dict sent to the server.

        Fields added after v1 are dropped entirely when left unset, so an older
        reporter emits exactly the message shape its version speaks: ``tags``
        (v2) and ``uuid`` (v3) each vanish when ``None``. A v1 reporter populates
        neither and so emits the pre-v2 shape; a v2 reporter sets ``tags`` (an
        empty tag list is still sent explicitly) but not ``uuid``; a v3 reporter
        sets both.
        """
        payload = asdict(self)
        if self.tags is None:
            del payload["tags"]
        if self.uuid is None:
            del payload["uuid"]
        return payload
