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

from collections.abc import Iterable
from typing import Any, Optional, Union

import requests

from .config import Settings
from .config import settings as _default_settings
from .contract import Criticity, normalize_criticity
from .protocol import Protocol, default_protocol, negotiate
from .reporter import _merge_tags
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
        tags: Run-wide tags (spec §3.1) applied to every bar; each bar's own
            tags are merged on top. Emitted only once a v2 server is negotiated.
        criticity: Run-wide task importance (spec §3.1), as a
            :class:`~webprogress_python.contract.Criticity` member (or the
            equivalent string): ``Criticity.TRIVIAL``, ``Criticity.STANDARD``,
            or ``Criticity.CRITICAL``. Applied to every bar unless the bar sets
            its own; an unrecognised value falls back to ``Criticity.STANDARD``.
            Emitted only once a v4 server is negotiated.
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
        tags: Optional[Iterable[str]] = None,
        criticity: Optional[Union[Criticity, str]] = None,
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
        self._tags: list[str] = _merge_tags(tags)
        # Run-wide task importance, normalised to a valid level (spec §3.1); a
        # bar may override it. Only emitted once a v4 server is negotiated.
        self._criticity: str = normalize_criticity(criticity)
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

    def tqdm(
        self,
        iterable: Optional[Iterable] = None,
        *,
        desc: Optional[str] = None,
        total: Optional[float] = None,
        leave: Optional[bool] = True,
        file: Optional[Any] = None,
        ncols: Optional[int] = None,
        mininterval: float = 0.1,
        maxinterval: float = 10.0,
        miniters: Optional[float] = None,
        ascii: Optional[Union[bool, str]] = None,  # noqa: A002 — mirrors tqdm's own name
        disable: Optional[bool] = False,
        unit: str = "it",
        unit_scale: Union[bool, float] = False,
        dynamic_ncols: bool = False,
        smoothing: float = 0.3,
        bar_format: Optional[str] = None,
        initial: float = 0,
        position: Optional[int] = None,
        postfix: Optional[dict] = None,
        unit_divisor: float = 1000,
        write_bytes: bool = False,
        lock_args: Optional[tuple] = None,
        nrows: Optional[int] = None,
        colour: Optional[str] = None,
        delay: Optional[float] = 0.0,
        gui: bool = False,
        tags: Optional[Iterable[str]] = None,
        criticity: Optional[Union[Criticity, str]] = None,
    ) -> _tqdm:
        """Create a progress bar bound to this tracker's config and protocol.

        Every parameter up to ``gui`` is a standard :class:`tqdm.std.tqdm`
        argument, forwarded unchanged. The two trailing parameters are the
        webprogress per-bar overrides (spec §3.1):

            tags: Labels for this bar, merged on top of the tracker's run-wide
                tags. Only emitted once a v2 server is negotiated.
            criticity: This bar's importance, overriding the tracker's run-wide
                value; a :class:`~webprogress_python.contract.Criticity` member
                (or the equivalent string). Only emitted once a v4 server is
                negotiated.

        Server coordinates, ``script``, HTTP session, and the negotiated
        protocol all come from the tracker.
        """
        return _tqdm(
            iterable,
            desc=desc,
            total=total,
            leave=leave,
            file=file,
            ncols=ncols,
            mininterval=mininterval,
            maxinterval=maxinterval,
            miniters=miniters,
            ascii=ascii,
            disable=disable,
            unit=unit,
            unit_scale=unit_scale,
            dynamic_ncols=dynamic_ncols,
            smoothing=smoothing,
            bar_format=bar_format,
            initial=initial,
            position=position,
            postfix=postfix,
            unit_divisor=unit_divisor,
            write_bytes=write_bytes,
            lock_args=lock_args,
            nrows=nrows,
            colour=colour,
            delay=delay,
            gui=gui,
            tags=tags,
            criticity=criticity,
            _tracker=self,
        )

    def trange(
        self,
        *range_args: int,
        desc: Optional[str] = None,
        total: Optional[float] = None,
        leave: Optional[bool] = True,
        file: Optional[Any] = None,
        ncols: Optional[int] = None,
        mininterval: float = 0.1,
        maxinterval: float = 10.0,
        miniters: Optional[float] = None,
        ascii: Optional[Union[bool, str]] = None,  # noqa: A002 — mirrors tqdm's own name
        disable: Optional[bool] = False,
        unit: str = "it",
        unit_scale: Union[bool, float] = False,
        dynamic_ncols: bool = False,
        smoothing: float = 0.3,
        bar_format: Optional[str] = None,
        initial: float = 0,
        position: Optional[int] = None,
        postfix: Optional[dict] = None,
        unit_divisor: float = 1000,
        write_bytes: bool = False,
        lock_args: Optional[tuple] = None,
        nrows: Optional[int] = None,
        colour: Optional[str] = None,
        delay: Optional[float] = 0.0,
        gui: bool = False,
        tags: Optional[Iterable[str]] = None,
        criticity: Optional[Union[Criticity, str]] = None,
    ) -> _tqdm:
        """Shortcut for ``self.tqdm(range(*range_args), ...)`` (mirrors tqdm.trange)."""
        return self.tqdm(
            range(*range_args),
            desc=desc,
            total=total,
            leave=leave,
            file=file,
            ncols=ncols,
            mininterval=mininterval,
            maxinterval=maxinterval,
            miniters=miniters,
            ascii=ascii,
            disable=disable,
            unit=unit,
            unit_scale=unit_scale,
            dynamic_ncols=dynamic_ncols,
            smoothing=smoothing,
            bar_format=bar_format,
            initial=initial,
            position=position,
            postfix=postfix,
            unit_divisor=unit_divisor,
            write_bytes=write_bytes,
            lock_args=lock_args,
            nrows=nrows,
            colour=colour,
            delay=delay,
            gui=gui,
            tags=tags,
            criticity=criticity,
        )
