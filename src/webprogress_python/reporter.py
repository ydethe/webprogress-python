"""The progress reporter (specification §4, architecture §3 steps 1-3).

``tqdm`` here is a drop-in replacement for :class:`tqdm.std.tqdm`. It behaves
identically for the local terminal display and adds one best-effort side
effect: on each display tick it mirrors the current progress state to the
webprogress server. Reporting is non-blocking and fault-tolerant — if the
server is down, slow, or rejecting, the update is silently dropped and the
tracked task continues unaffected.

The *shape* of each update is decided by a :class:`~webprogress_python.protocol.base.Protocol`
(spec §6.6): a standalone bar speaks the default protocol, while a bar created
through a :class:`~webprogress_python.tracker.Tracker` speaks whichever protocol
the tracker negotiated from the server's ``/version``.
"""

from __future__ import annotations

import getpass
import socket
import threading
import uuid as _uuid
from typing import TYPE_CHECKING, Iterable

import requests
from tqdm.std import tqdm as _std_tqdm

from .config import Settings
from .config import settings as _default_settings
from .protocol import Protocol, ReportSnapshot, default_protocol

if TYPE_CHECKING:
    from .tracker import Tracker

# A short send timeout keeps reporting from ever slowing the tracked task
# beyond this bound (spec §4). Tuple is (connect, read) seconds.
_DEFAULT_TIMEOUT: tuple = (1.0, 1.0)

# Cheap to compute once per process; stable for the program's lifetime.
_HOSTNAME = socket.gethostname()
try:
    _LOGIN = getpass.getuser()
except Exception:  # getuser can raise if no account info is available
    _LOGIN = ""


def _merge_tags(*groups: None | Iterable[str]) -> list[str]:
    """Flatten tag groups into one list, de-duplicated and order-preserving.

    Used to combine a tracker's run-wide tags with a bar's own tags (spec §3.1):
    tags are additive labels, so both contribute and duplicates collapse.
    """
    merged: list[str] = []
    for group in groups:
        if not group:
            continue
        for tag in group:
            if tag not in merged:
                merged.append(tag)
    return merged


class tqdm(_std_tqdm):  # noqa: N801 — mirrors tqdm's own lowercase class name
    """tqdm progress bar that mirrors each tick to a webprogress server.

    Extra keyword arguments beyond standard tqdm:

        endpoint: A :class:`~webprogress_python.config.Settings` (or any object
            exposing ``host`` and ``key``) giving the server coordinates.
            Defaults to the module-level settings loaded from the environment.
        host: Server base address; overrides ``endpoint.host`` when given.
        key: Credential token; overrides ``endpoint.key`` when given.
        script: Script the task belongs to (spec §3.1); groups tasks on the
            dashboard. Defaults to empty ("unscripted").
        tags: Free-form labels attached to the task (spec §3.1), shown as chips
            on the dashboard. Only emitted once a v2 server has been negotiated.
            A tracker-driven bar merges these with the tracker's own tags.
        report_timeout: Per-send timeout, as seconds or a (connect, read) tuple.

    Values supplied directly (``host`` / ``key``) take precedence over
    ``endpoint``, which in turn comes from the environment (spec §5).

    Bars created via :meth:`Tracker.tqdm <webprogress_python.tracker.Tracker.tqdm>`
    inherit the tracker's resolved configuration, HTTP session, script, tags,
    and negotiated protocol through the internal ``_tracker`` argument.
    """

    def __init__(
        self,
        *args,
        endpoint: None | Settings = None,
        host: None | str = None,
        key: None | str = None,
        script: str = "",
        tags: None | Iterable[str] = None,
        report_timeout: None | float | tuple = None,
        _tracker: None | "Tracker" = None,
        **kwargs,
    ):
        if _tracker is not None:
            # Driven by a Tracker: share its config, session, script, and the
            # protocol it already negotiated (spec §6.6). The tracker owns the
            # session's lifetime, so this bar must not close it.
            self._wp_host = _tracker._wp_host
            self._wp_key = _tracker._wp_key
            self._wp_timeout = _tracker._wp_timeout
            self._wp_session = _tracker._wp_session
            self._wp_script = _tracker._script
            self._wp_protocol = _tracker._protocol
            self._wp_owns_session = False
            # Tags are additive: the bar's own tags join the tracker's run-wide
            # tags (spec §3.1).
            self._wp_tags = _merge_tags(_tracker._tags, tags)
        else:
            source = endpoint if endpoint is not None else _default_settings
            resolved_host = host if host is not None else getattr(source, "host", "")
            resolved_key = key if key is not None else getattr(source, "key", "")

            self._wp_host = (resolved_host or "").rstrip("/")
            self._wp_key = resolved_key or ""
            self._wp_timeout = report_timeout if report_timeout is not None else _DEFAULT_TIMEOUT
            self._wp_session = requests.Session()
            self._wp_script = script or ""
            # A standalone bar speaks the current protocol without a handshake;
            # negotiation is a Tracker concern (spec §4: handshake is optional).
            self._wp_protocol: Protocol = default_protocol()
            self._wp_owns_session = True
            self._wp_tags = _merge_tags(tags)

        # Identity of this run (spec §3.1/§6.3): one uuid per bar, minted here and
        # sent unchanged on every tick. A new bar — e.g. a restarted task — mints a
        # new uuid, so the server opens a fresh dashboard card for it. Only emitted
        # once a v3 server has been negotiated; older protocols ignore it.
        self._wp_uuid = str(_uuid.uuid4())

        # Serializes sends onto the shared HTTP session; acquired non-blocking so
        # a tick triggered while another is in flight (e.g. from tqdm's own
        # monitor thread) is skipped rather than made to wait.
        self._wp_lock = threading.Lock()

        super().__init__(*args, **kwargs)

    # --- reporting side effect -------------------------------------------------

    def display(self, msg: None | str = None, pos: None | int = None):
        """Render the local bar (always, first), then mirror to the server.

        tqdm calls ``display`` on every refresh. A clear passes ``msg=''``; the
        reporter sends nothing on a clear — clearing affects only the local
        display (spec §4).
        """
        rendered = super().display(msg=msg, pos=pos)
        if msg != "":
            self._report()
        return rendered

    def _build_payload(self) -> dict:
        """Capture current state and let the active protocol shape it (§4.2, §6.6)."""
        snapshot = ReportSnapshot(
            user_hostname=_HOSTNAME,
            user_login=_LOGIN,
            script=self._wp_script,
            description=self.desc or "",
            colour=self.colour,
            key=self._wp_key,
            format_dict=self.format_dict,
            tags=self._wp_tags,
            uuid=self._wp_uuid,
        )
        return self._wp_protocol.build_payload(snapshot)

    def _report(self) -> None:
        """Send one update, best-effort. Never raises into the tracked task.

        The send runs under a non-blocking lock: if another send is already in
        flight on the shared session, this call is skipped rather than made to
        wait.

        Sends nothing when there is no host, or when the negotiated protocol is
        unsupported (the server advertised a version this client can't speak;
        see :func:`webprogress_python.protocol.negotiate`).
        """
        if not self._wp_host or not self._wp_protocol.supported:
            return
        if not self._wp_lock.acquire(blocking=False):
            return
        try:
            payload = self._build_payload()
            self._wp_session.post(
                self._wp_host + self._wp_protocol.ingest_path,
                json=payload,
                timeout=self._wp_timeout,
            )
        except Exception:
            # Any transport-level failure or rejection is caught and ignored;
            # the reporter never inspects the response (spec §4).
            pass
        finally:
            self._wp_lock.release()

    def close(self) -> None:
        """Close the bar, then release the session if we own it."""
        try:
            super().close()
        finally:
            if self._wp_owns_session:
                try:
                    self._wp_session.close()
                except Exception:
                    pass


def trange(*args, **kwargs) -> tqdm:
    """Shortcut for ``tqdm(range(*args), **kwargs)`` (mirrors tqdm.trange)."""
    return tqdm(range(*args), **kwargs)
