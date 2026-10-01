"""Minimal usage example.

Configure the server via the environment (or a local `.env`) before running:

    WEBPROGRESS_HOST=http://localhost:8775
    WEBPROGRESS_KEY=<your credential token>
"""

import time

from webprogress_python import tqdm
from webprogress_python.config import settings


# `settings` carries the webprogress server configuration: host and key.
def test_client():
    for a in tqdm(range(10), desc="foo", endpoint=settings):
        time.sleep(1)


if __name__ in {"__main__", "__mp_main__"}:
    test_client()
