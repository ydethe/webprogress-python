"""The progress reporter (specification §4, architecture §3 steps 1-3).

``tqdm`` here is a drop-in replacement for :class:`tqdm.std.tqdm`. It behaves
identically for the local terminal display and adds one best-effort side
effect: on each display tick it mirrors the current progress state to the
webprogress server. Reporting is non-blocking and fault-tolerant — if the
server is down, slow, or rejecting, the update is silently dropped and the
tracked task continues unaffected.
"""

from __future__ import annotations

import getpass
import socket
from typing import Any, Optional, Union

import requests
from tqdm.std import tqdm as _std_tqdm

from .config import Settings
from .config import settings as _default_settings
from .contract import (
    DEFAULT_COLOUR,
    DEFAULT_INITIAL,
    DEFAULT_RATE,
    ProgressUpdate,
)

# The update-ingest endpoint (spec §8, architecture §4).
_INGEST_PATH = "/handler"

# A short send timeout keeps reporting from ever slowing the tracked task
# beyond this bound (spec §4). Tuple is (connect, read) seconds.
_DEFAULT_TIMEOUT: tuple = (1.0, 1.0)

# Cheap to compute once per process; stable for the program's lifetime.
_HOSTNAME = socket.gethostname()
try:
    _LOGIN = getpass.getuser()
except Exception:  # getuser can raise if no account info is available
    _LOGIN = ""


class tqdm(_std_tqdm):  # noqa: N801 — mirrors tqdm's own lowercase class name
    """tqdm progress bar that mirrors each tick to a webprogress server.

    Extra keyword arguments beyond standard tqdm:

        endpoint: A :class:`~webprogress_python.config.Settings` (or any object
            exposing ``host`` and ``key``) giving the server coordinates.
            Defaults to the module-level settings loaded from the environment.
        host: Server base address; overrides ``endpoint.host`` when given.
        key: Credential token; overrides ``endpoint.key`` when given.
        report_timeout: Per-send timeout, as seconds or a (connect, read) tuple.

    Values supplied directly (``host`` / ``key``) take precedence over
    ``endpoint``, which in turn comes from the environment (spec §5).
    """

    def __init__(
        self,
        *args,
        endpoint: Optional[Settings] = None,
        host: Optional[str] = None,
        key: Optional[str] = None,
        report_timeout: Optional[Union[float, tuple]] = None,
        **kwargs,
    ):
        source = endpoint if endpoint is not None else _default_settings
        resolved_host = host if host is not None else getattr(source, "host", "")
        resolved_key = key if key is not None else getattr(source, "key", "")

        self._wp_host = (resolved_host or "").rstrip("/")
        self._wp_key = resolved_key or ""
        self._wp_timeout = report_timeout if report_timeout is not None else _DEFAULT_TIMEOUT
        self._wp_session = requests.Session()

        super().__init__(*args, **kwargs)

    # --- reporting side effect -------------------------------------------------

    def display(self, msg: Optional[str] = None, pos: Optional[int] = None):
        """Render the local bar (always, first), then mirror to the server.

        tqdm calls ``display`` on every refresh. A clear passes ``msg=''``; the
        reporter sends nothing on a clear — clearing affects only the local
        display (spec §4).
        """
        rendered = super().display(msg=msg, pos=pos)
        if msg != "":
            self._report()
        return rendered

    def _build_update(self) -> ProgressUpdate:
        """Capture current progress state as one update message (spec §4.2)."""
        d = self.format_dict
        return ProgressUpdate(
            user_hostname=_HOSTNAME,
            user_login=_LOGIN,
            progress=d.get("n"),
            total=d.get("total"),
            description=self.desc or "",
            elapsed=d.get("elapsed"),
            unit=d.get("unit"),
            unit_scale=d.get("unit_scale"),
            # Fallback defaults for values not yet available (spec §4.3).
            rate=d.get("rate") or DEFAULT_RATE,
            unit_divisor=d.get("unit_divisor"),
            initial=d.get("initial") or DEFAULT_INITIAL,
            colour=self.colour or DEFAULT_COLOUR,
            key=self._wp_key,
            # Reporter leaves this empty; the server stamps it (spec §3.2).
            user_src_address="",
        )

    def _report(self) -> None:
        """Send one update, best-effort. Never raises into the tracked task."""
        if not self._wp_host:
            return
        try:
            payload = self._build_update().to_payload()
            self._wp_session.post(
                self._wp_host + _INGEST_PATH,
                json=payload,
                timeout=self._wp_timeout,
            )
        except Exception:
            # Any transport-level failure or rejection is caught and ignored;
            # the reporter never inspects the response (spec §4).
            pass

    def close(self) -> None:
        """Close the bar, then release the HTTP session (best-effort)."""
        try:
            super().close()
        finally:
            try:
                self._wp_session.close()
            except Exception:
                pass


def trange(*args, **kwargs) -> tqdm:
    """Shortcut for ``tqdm(range(*args), **kwargs)`` (mirrors tqdm.trange)."""
    return tqdm(range(*args), **kwargs)
