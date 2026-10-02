"""webprogress-python — the progress-reporter client.

A drop-in ``tqdm`` that renders the usual local progress bar and additionally
mirrors each tick, best-effort, to a webprogress server.

Standalone, for a single progress bar::

    from webprogress_python import tqdm
    from webprogress_python.config import settings

    for item in tqdm(range(10), desc="foo", endpoint=settings):
        ...

Or via a :class:`~webprogress_python.tracker.Tracker`, which groups several bars
under one ``script`` and negotiates the server's wire protocol once (spec §6.6)::

    from webprogress_python import Tracker
    from webprogress_python.config import settings

    with Tracker(script="basic.py", endpoint=settings) as t:
        for item in t.tqdm(range(10), desc="foo"):
            ...
"""

from .config import Settings, settings
from .contract import Criticity
from .reporter import tqdm, trange
from .tracker import Tracker

__all__ = ["Settings", "settings", "Tracker", "Criticity", "tqdm", "trange"]
