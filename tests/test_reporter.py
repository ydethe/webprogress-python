"""Tests for the progress reporter (spec §4, §5; contract §3)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from webprogress_python import Tracker, tqdm
from webprogress_python.config import Settings
from webprogress_python.contract import DEFAULT_COLOUR

CONTRACT_FIELDS = {
    "user_hostname",
    "user_login",
    "script",
    "progress",
    "total",
    "description",
    "elapsed",
    "unit",
    "unit_scale",
    "rate",
    "unit_divisor",
    "initial",
    "colour",
    "user_src_address",
    "key",
}


@pytest.fixture
def server():
    """A tiny server that records every POSTed update, on an ephemeral port."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            received.append((self.path, json.loads(self.rfile.read(n) or b"{}")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{srv.server_address[1]}"
    yield host, received
    srv.shutdown()


def test_reports_full_contract_to_handler(server):
    host, received = server
    settings = Settings(host=host, key="tok-123")

    for _ in tqdm(range(5), desc="foo", endpoint=settings):
        pass
    time.sleep(0.1)

    assert received, "expected at least one update"
    assert {p for p, _ in received} == {"/handler"}
    last = received[-1][1]
    assert set(last.keys()) == CONTRACT_FIELDS
    assert last["key"] == "tok-123"
    assert last["description"] == "foo"
    assert last["total"] == 5
    assert last["progress"] == 5
    assert last["user_src_address"] == ""  # reporter leaves it empty (§3.2)


def test_fallback_defaults_applied(server):
    host, received = server
    for _ in tqdm(range(1), endpoint=Settings(host=host, key="k")):
        pass
    time.sleep(0.1)
    payload = received[0][1]
    assert payload["rate"] == 0  # no rate yet on the first tick (§4.3)
    assert payload["initial"] == 0
    assert payload["colour"] == DEFAULT_COLOUR


def test_direct_args_override_endpoint(server):
    host, received = server
    endpoint = Settings(host="http://unused.invalid", key="env-key")
    # Direct host/key take precedence over endpoint (spec §5).
    for _ in tqdm(range(1), endpoint=endpoint, host=host, key="direct-key"):
        pass
    time.sleep(0.1)
    assert received[-1][1]["key"] == "direct-key"


def test_dead_server_does_not_break_loop():
    # Port 9 (discard) refuses immediately; loop must still complete.
    start = time.time()
    count = sum(
        1 for _ in tqdm(range(5), host="http://127.0.0.1:9", key="k", report_timeout=(0.5, 0.5))
    )
    assert count == 5
    assert time.time() - start < 2.0


def test_missing_config_is_noop():
    # No host configured -> reporting is skipped, iteration still works.
    count = sum(1 for _ in tqdm(range(3), host="", key=""))
    assert count == 3


@pytest.fixture
def versioned_server():
    """A server that answers GET /version and records POSTed updates."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version_advertised = 1

        def do_GET(self):
            if self.path == "/version":
                body = json.dumps(
                    {"name": "webprogress", "version": "test", "protocol": 1}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            received.append((self.path, json.loads(self.rfile.read(n) or b"{}")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{srv.server_address[1]}"
    yield host, received
    srv.shutdown()


def test_tracker_negotiates_and_reports_script(versioned_server):
    host, received = versioned_server
    settings = Settings(host=host, key="tok-xyz")

    with Tracker(script="basic.py", endpoint=settings) as t:
        assert t.protocol_version == 1  # negotiated from GET /version
        for _ in t.tqdm(range(3), desc="foo"):
            pass
    time.sleep(0.1)

    assert received, "expected at least one update"
    assert {p for p, _ in received} == {"/handler"}
    last = received[-1][1]
    assert set(last.keys()) == CONTRACT_FIELDS
    assert last["script"] == "basic.py"  # tracker's script is on the wire (§3.1)
    assert last["description"] == "foo"
    assert last["key"] == "tok-xyz"


def test_tracker_falls_back_without_version_endpoint(server):
    # The plain `server` fixture has no /version; handshake must fall back (§6.6).
    host, received = server
    with Tracker(script="s", host=host, key="k") as t:
        assert t.protocol_version == 1  # default protocol
        for _ in t.tqdm(range(2), desc="d"):
            pass
    time.sleep(0.1)
    assert received[-1][1]["script"] == "s"


def test_tracker_dead_server_does_not_break_loop():
    # Unreachable server: handshake and reporting are both best-effort.
    start = time.time()
    with Tracker(script="s", host="http://127.0.0.1:9", key="k", report_timeout=(0.5, 0.5)) as t:
        count = sum(1 for _ in t.tqdm(range(5), desc="d"))
    assert count == 5
    assert time.time() - start < 3.0
