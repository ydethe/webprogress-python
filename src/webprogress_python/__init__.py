"""webprogress-python — the progress-reporter client.

A drop-in ``tqdm`` that renders the usual local progress bar and additionally
mirrors each tick, best-effort, to a webprogress server.

    from webprogress_python import tqdm
    from webprogress_python.config import settings

    for item in tqdm(range(10), desc="foo", endpoint=settings):
        ...
"""

from .config import Settings, settings
from .reporter import tqdm, trange

__all__ = ["Settings", "settings", "tqdm", "trange"]
