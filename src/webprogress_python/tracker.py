"""The Tracker — a session-scoped handle for a script's progress bars.

A :class:`Tracker` bundles the three things a group of related progress bars
share: the server coordinates (spec §5), the ``script`` the tasks belong to
(spec §3.1), and a single HTTP session. On entry it performs the ``/version``
handshake **once** (spec §6.6) and hands every bar it creates the negotiated
protocol, so the version is chosen per server rather than per bar.

    from webprogress_python import Tracker
    from webprogress_python.config import settings

    with Tracker(script="basic.py", endpoint=settings) as t:
        for item in t.tqdm(range(10), desc="foo"):
            ...

The handshake is best-effort: if the server is unreachable or does not advertise
``/version``, the tracker simply speaks the default protocol (spec §4).
"""

from __future__ import annotations

from typing import Optional, Union

import requests

from .config import Settings
from .config import settings as _default_settings
from .protocol import Protocol, default_protocol, negotiate
from .reporter import tqdm as _tqdm

_DEFAULT_TIMEOUT: tuple = (1.0, 1.0)


class Tracker:
    """Groups progress bars under one script, server, and negotiated protocol.

    Arguments mirror the standalone reporter (spec §5): ``host`` / ``key`` given
    directly take precedence over ``endpoint``, which defaults to the
    environment-loaded settings.

        script: Script the grouped tasks belong to (spec §3.1).
        endpoint: Settings-like object exposing ``host`` and ``key``.
        host / key: Direct overrides for the server address and credential.
        report_timeout: Per-send timeout, as seconds or a (connect, read) tuple;
            also bounds the handshake request.
    """

    def __init__(
        self,
        script: str = "",
        *,
        endpoint: Optional[Settings] = None,
        host: Optional[str] = None,
        key: Optional[str] = None,
        report_timeout: Optional[Union[float, tuple]] = None,
    ):
        source = endpoint if endpoint is not None else _default_settings
        resolved_host = host if host is not None else getattr(source, "host", "")
        resolved_key = key if key is not None else getattr(source, "key", "")

        self._script = script or ""
        self._wp_host = (resolved_host or "").rstrip("/")
        self._wp_key = resolved_key or ""
        self._wp_timeout = report_timeout if report_timeout is not None else _DEFAULT_TIMEOUT
        self._wp_session = requests.Session()
        # Replaced by the negotiated protocol on __enter__; a sensible default
        # so bars built outside a ``with`` block still work.
        self._protocol: Protocol = default_protocol()

    def __enter__(self) -> "Tracker":
        # One best-effort §6.6 handshake for the whole tracker.
        self._protocol = negotiate(self._wp_host, self._wp_session, self._wp_timeout)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self._wp_session.close()
        except Exception:
            pass
        return False  # never suppress exceptions from the tracked task

    @property
    def protocol_version(self) -> int:
        """The wire-protocol version this tracker negotiated (spec §6.6)."""
        return self._protocol.version

    def tqdm(self, *args, **kwargs) -> _tqdm:
        """Create a progress bar bound to this tracker's config and protocol."""
        return _tqdm(*args, _tracker=self, **kwargs)

    def trange(self, *args, **kwargs) -> _tqdm:
        """Shortcut for ``self.tqdm(range(*args), **kwargs)``."""
        return self.tqdm(range(*args), **kwargs)
