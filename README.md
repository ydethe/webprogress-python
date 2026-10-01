# webprogress-python

The **progress-reporter** client for [webprogress](./docs/01-specification.md): a
drop-in `tqdm` that renders the usual local progress bar **and** mirrors each
tick, best-effort, to a webprogress server so you can watch a long-running task
from your browser dashboard.

Reporting is a transparent side effect — if the server is down, slow, or
rejecting, updates are silently dropped and your task runs unaffected.

## Install

```bash
uv pip install -e .      # or: pip install -e .
```

## Configure

The reporter needs two inputs — a **server base address** and a **credential
token** (minted in the web UI). Supply them via the environment (optionally a
local `.env`):

```bash
export WEBPROGRESS_HOST=http://localhost:8775
export WEBPROGRESS_KEY=<your credential token>
```

…or directly in code, which takes precedence over the environment.

## Use

```python
import time

from webprogress_python import tqdm
from webprogress_python.config import settings

for a in tqdm(range(10), desc="foo", endpoint=settings):
    time.sleep(1)
```

`tqdm` accepts all standard tqdm arguments plus:

| Argument | Meaning |
| --- | --- |
| `endpoint` | A `Settings` (or anything with `host`/`key`); defaults to the env-loaded `settings`. |
| `host` | Server base address; overrides `endpoint.host`. |
| `key` | Credential token; overrides `endpoint.key`. |
| `report_timeout` | Per-send timeout in seconds, or a `(connect, read)` tuple. |

## How it works

On each display tick the reporter draws the local bar first, builds one update
message from the current progress state (the [shared contract](./docs/01-specification.md#3-progress-update-contract-the-wire-payload)),
attaches the token, and POSTs it to the server's `/handler` endpoint with a
short timeout. Any transport failure or rejection is caught and ignored.

## Develop

```bash
uv pip install -e '.[dev]'
pytest
```
