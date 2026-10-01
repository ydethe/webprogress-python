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
| `script` | Script the task belongs to; groups tasks on the dashboard. |
| `tags` | Free-form labels shown as chips on the dashboard (protocol v2). |
| `report_timeout` | Per-send timeout in seconds, or a `(connect, read)` tuple. |

`tags` was added in **protocol version 2**. It is only put on the wire once the
client has negotiated a v2 server through the
`/version` handshake — which a [`Tracker`](./docs/01-specification.md#66-version-advertisement-handshake)
does automatically. Against a v1 server it is silently omitted.

If the handshake finds the server advertising a protocol version this client
**does not implement** (e.g. a newer server), the client cannot safely shape a
message for it: it emits an `UnsupportedProtocolWarning` and **disables
reporting** for that session — nothing is sent to the server. The tracked task
still runs unaffected. (A server that is simply unreachable or that advertises
no version is different: the client falls back to its default protocol and keeps
reporting best-effort.)

A `Tracker` can set run-wide `tags` for every bar it creates; a bar's own `tags`
merge on top:

```python
with Tracker(script="train.py", tags=["gpu", "nightly"]) as t:
    for _ in t.tqdm(range(1000), desc="epoch 3/12", tags=["batch-7"]):
        ...
```

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
