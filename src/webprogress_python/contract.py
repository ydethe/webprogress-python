"""The shared update contract (specification §3, architecture §2).

This is the single message definition shared by reporter and server. The
reporter serializes exactly these fields; the server validates incoming
messages against exactly these fields. Any change here is a contract change
that touches both sides at once.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any

# Fallback defaults applied when a value is not yet available (spec §4.3).
DEFAULT_RATE = 0.0
DEFAULT_INITIAL = 0
DEFAULT_COLOUR = "#0000ff"  # standard blue

# Identity of this reporting client library (spec §3.1, protocol v4): the
# dashboard shows it as the chip ``library@library_version``.
LIBRARY_NAME = "webprogress"


# The task's importance, which gates its out-of-band notifications (spec §3.1,
# §6.7, protocol v4). An absent or unrecognised value falls back to the default.
class Criticity(str, Enum):
    """A task's importance, which gates its out-of-band notifications (spec §3.1, §6.7).

    A ``str`` enum, so a member compares and serializes as its wire value: e.g.
    ``Criticity.CRITICAL == "critical"`` and it JSON-encodes to ``"critical"``.
    """

    TRIVIAL = "trivial"
    STANDARD = "standard"
    CRITICAL = "critical"


# The valid wire levels and the default, derived from the enum so there is a
# single source of truth. Both are plain strings — the shape sent on the wire.
CRITICITY_LEVELS = tuple(level.value for level in Criticity)
DEFAULT_CRITICITY = Criticity.STANDARD.value


def library_version() -> str:
    """Version of this installed client library (spec §3.1); empty if unknown."""
    try:
        return _pkg_version("webprogress_python")
    except PackageNotFoundError:
        return ""


def normalize_criticity(value: Criticity | str | None) -> str:
    """Map a criticity to a valid level string, defaulting unknown ones (spec §3.1).

    Accepts a :class:`Criticity` member or its string value; anything else
    (including ``None`` or an unrecognised string) falls back to the default.
    """
    if isinstance(value, Criticity):
        return value.value
    if value in CRITICITY_LEVELS:
        return value
    return DEFAULT_CRITICITY


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

    # --- Display fields added at protocol v4 (§3.1) ---
    # Name and version of the reporting client library, shown together as the
    # chip ``library@library_version``; not part of a task's identity. A pre-v4
    # reporter omits both fields entirely (see ``to_payload``).
    library: str | None = None
    library_version: str | None = None
    # Importance of the task (``trivial`` / ``standard`` / ``critical``), which
    # gates its out-of-band notifications (§6.7); not part of a task's identity.
    # A pre-v4 reporter omits the field, and the server falls back to the default
    # ``standard``.
    criticity: str | None = None

    def to_payload(self) -> dict:
        """Serialize to the JSON-ready dict sent to the server.

        Fields added after v1 are dropped entirely when left unset, so an older
        reporter emits exactly the message shape its version speaks: ``tags``
        (v2), ``uuid`` (v3), and ``library`` / ``library_version`` / ``criticity``
        (v4) each vanish when ``None``. A v1 reporter populates none of them and so
        emits the pre-v2 shape; a v2 reporter sets ``tags`` (an empty tag list is
        still sent explicitly) only; a v3 reporter also sets ``uuid``; a v4 reporter
        additionally sets the three v4 fields.
        """
        payload = asdict(self)
        for name in ("tags", "uuid", "library", "library_version", "criticity"):
            if getattr(self, name) is None:
                del payload[name]
        return payload
