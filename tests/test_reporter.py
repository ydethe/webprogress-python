"""Tests for the progress reporter (spec §4, §5; contract §3)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from webprogress_python import Criticity, Tracker, tqdm
from webprogress_python.config import Settings
from webprogress_python.contract import DEFAULT_COLOUR
from webprogress_python.protocol import UnsupportedProtocolWarning

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

# Protocol v2 adds one optional display field (spec §3.1).
CONTRACT_FIELDS_V2 = CONTRACT_FIELDS | {"tags"}

# Protocol v3 adds the reporter-assigned per-run uuid (spec §3.1).
CONTRACT_FIELDS_V3 = CONTRACT_FIELDS_V2 | {"uuid"}

# Protocol v4 adds the reporting library and the task criticity (spec §3.1).
CONTRACT_FIELDS_V4 = CONTRACT_FIELDS_V3 | {"library", "library_version", "criticity"}


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


def _version_server(protocol: int):
    """Spin up a server advertising `protocol` on GET /version; records POSTs."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/version":
                body = json.dumps(
                    {"name": "webprogress", "version": "test", "protocol": protocol}
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
    return srv, host, received


@pytest.fixture
def versioned_server_v2():
    """A server that advertises protocol 2 and records POSTed updates."""
    srv, host, received = _version_server(2)
    yield host, received
    srv.shutdown()


def test_tracker_negotiates_v2_and_emits_new_fields(versioned_server_v2):
    host, received = versioned_server_v2
    settings = Settings(host=host, key="tok-v2")

    with Tracker(script="train.py", endpoint=settings, tags=["gpu", "nightly"]) as t:
        assert t.protocol_version == 2  # negotiated from GET /version
        for _ in t.tqdm(range(3), desc="epoch"):
            pass
    time.sleep(0.1)

    assert received, "expected at least one update"
    last = received[-1][1]
    assert set(last.keys()) == CONTRACT_FIELDS_V2  # tags present
    assert last["tags"] == ["gpu", "nightly"]
    assert last["script"] == "train.py"


def test_tracker_merges_run_and_bar_tags(versioned_server_v2):
    host, received = versioned_server_v2
    with Tracker(host=host, key="k", tags=["gpu", "nightly"]) as t:
        # Bar adds its own tag; the shared "gpu" collapses, order preserved.
        for _ in t.tqdm(range(2), desc="d", tags=["gpu", "batch-7"]):
            pass
    time.sleep(0.1)
    assert received[-1][1]["tags"] == ["gpu", "nightly", "batch-7"]


def test_v1_server_omits_v2_fields(versioned_server):
    # A v1 server must never receive the optional v2 fields (spec §3.1).
    host, received = versioned_server
    with Tracker(host=host, key="k", tags=["gpu"]) as t:
        assert t.protocol_version == 1
        for _ in t.tqdm(range(2), desc="d"):
            pass
    time.sleep(0.1)
    last = received[-1][1]
    assert set(last.keys()) == CONTRACT_FIELDS
    assert "tags" not in last


@pytest.fixture
def versioned_server_v3():
    """A server that advertises protocol 3 and records POSTed updates."""
    srv, host, received = _version_server(3)
    yield host, received
    srv.shutdown()


def test_tracker_negotiates_v3_and_emits_uuid(versioned_server_v3):
    host, received = versioned_server_v3
    settings = Settings(host=host, key="tok-v3")

    with Tracker(script="train.py", endpoint=settings, tags=["gpu"]) as t:
        assert t.protocol_version == 3  # negotiated from GET /version
        for _ in t.tqdm(range(3), desc="epoch"):
            pass
    time.sleep(0.1)

    assert received, "expected at least one update"
    last = received[-1][1]
    assert set(last.keys()) == CONTRACT_FIELDS_V3  # tags and uuid present
    assert last["script"] == "train.py"
    assert last["tags"] == ["gpu"]
    # The uuid is a non-empty reporter-assigned run identity (spec §3.1/§6.3).
    assert last["uuid"]


def test_v3_uuid_is_stable_within_a_run(versioned_server_v3):
    # One bar is one run: every tick carries the same uuid (spec §6.3).
    host, received = versioned_server_v3
    with Tracker(host=host, key="k") as t:
        for _ in t.tqdm(range(4), desc="d"):
            pass
    time.sleep(0.1)
    uuids = {payload["uuid"] for _, payload in received}
    assert len(uuids) == 1  # stable across the run's ticks


def test_v3_distinct_runs_get_distinct_uuids(versioned_server_v3):
    # A restarted task (a new bar) mints a fresh uuid, so the server opens a new
    # dashboard card rather than reviving the old run (spec §6.3).
    host, received = versioned_server_v3
    with Tracker(host=host, key="k") as t:
        for _ in t.tqdm(range(2), desc="d"):
            pass
        for _ in t.tqdm(range(2), desc="d"):
            pass
    time.sleep(0.1)
    uuids = {payload["uuid"] for _, payload in received}
    assert len(uuids) == 2  # one per run


def test_v2_server_omits_v3_uuid(versioned_server_v2):
    # A v2 server must never receive the v3 uuid field (spec §3.1).
    host, received = versioned_server_v2
    with Tracker(host=host, key="k", tags=["gpu"]) as t:
        assert t.protocol_version == 2
        for _ in t.tqdm(range(2), desc="d"):
            pass
    time.sleep(0.1)
    last = received[-1][1]
    assert set(last.keys()) == CONTRACT_FIELDS_V2
    assert "uuid" not in last


@pytest.fixture
def versioned_server_v4():
    """A server that advertises protocol 4 and records POSTed updates."""
    srv, host, received = _version_server(4)
    yield host, received
    srv.shutdown()


def test_tracker_negotiates_v4_and_emits_library_and_criticity(versioned_server_v4):
    host, received = versioned_server_v4
    settings = Settings(host=host, key="tok-v4")

    with Tracker(script="train.py", endpoint=settings, tags=["gpu"], criticity="critical") as t:
        assert t.protocol_version == 4  # negotiated from GET /version
        for _ in t.tqdm(range(3), desc="epoch"):
            pass
    time.sleep(0.1)

    assert received, "expected at least one update"
    last = received[-1][1]
    assert set(last.keys()) == CONTRACT_FIELDS_V4  # library trio present
    assert last["script"] == "train.py"
    assert last["tags"] == ["gpu"]
    assert last["uuid"]  # v3 field still carried
    assert last["library"] == "webprogress"  # the reporting client (spec §3.1)
    assert isinstance(last["library_version"], str)  # the installed version
    assert last["criticity"] == "critical"


def test_v4_criticity_defaults_to_standard(versioned_server_v4):
    # An unset criticity is sent as the default level (spec §3.1).
    host, received = versioned_server_v4
    with Tracker(host=host, key="k") as t:
        for _ in t.tqdm(range(2), desc="d"):
            pass
    time.sleep(0.1)
    assert received[-1][1]["criticity"] == "standard"


def test_v4_unknown_criticity_falls_back_to_standard(versioned_server_v4):
    # An unrecognised criticity is normalised to the default (spec §3.1).
    host, received = versioned_server_v4
    with Tracker(host=host, key="k", criticity="bogus") as t:
        for _ in t.tqdm(range(2), desc="d"):
            pass
    time.sleep(0.1)
    assert received[-1][1]["criticity"] == "standard"


def test_v4_bar_criticity_overrides_tracker(versioned_server_v4):
    # A bar's own criticity takes precedence over the tracker's run-wide one.
    host, received = versioned_server_v4
    with Tracker(host=host, key="k", criticity="trivial") as t:
        for _ in t.tqdm(range(2), desc="d", criticity="critical"):
            pass
    time.sleep(0.1)
    assert received[-1][1]["criticity"] == "critical"


def test_v4_criticity_accepts_criticity_enum(versioned_server_v4):
    # A Criticity enum member is accepted on both the tracker and the bar, and
    # is serialised to its plain wire string (spec §3.1).
    host, received = versioned_server_v4
    with Tracker(host=host, key="k", criticity=Criticity.TRIVIAL) as t:
        for _ in t.tqdm(range(2), desc="d", criticity=Criticity.CRITICAL):
            pass
    time.sleep(0.1)
    assert received[-1][1]["criticity"] == "critical"


def test_v3_server_omits_v4_fields(versioned_server_v3):
    # A v3 server must never receive the v4 library/criticity fields (spec §3.1).
    host, received = versioned_server_v3
    with Tracker(host=host, key="k", criticity="critical") as t:
        assert t.protocol_version == 3
        for _ in t.tqdm(range(2), desc="d"):
            pass
    time.sleep(0.1)
    last = received[-1][1]
    assert set(last.keys()) == CONTRACT_FIELDS_V3
    assert "library" not in last
    assert "library_version" not in last
    assert "criticity" not in last


@pytest.fixture
def versioned_server_unsupported():
    """A server advertising a protocol version this client does not implement."""
    srv, host, received = _version_server(99)
    yield host, received
    srv.shutdown()


def test_unsupported_protocol_warns_and_sends_nothing(versioned_server_unsupported):
    host, received = versioned_server_unsupported

    with pytest.warns(UnsupportedProtocolWarning, match="protocol version 99"):
        with Tracker(host=host, key="k") as t:
            assert t.protocol_version == 99  # the advertised, unsupported version
            for _ in t.tqdm(range(5), desc="d"):
                pass
    time.sleep(0.2)

    # Reporting is disabled under an unsupported protocol: no updates reach /handler.
    assert received == []


def test_unsupported_protocol_does_not_break_loop(versioned_server_unsupported):
    host, _received = versioned_server_unsupported
    with pytest.warns(UnsupportedProtocolWarning):
        with Tracker(host=host, key="k") as t:
            count = sum(1 for _ in t.tqdm(range(5), desc="d"))
    assert count == 5  # the tracked task runs unaffected
