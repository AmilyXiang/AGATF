"""Tests for the Action URL listener and the closed-loop verification.

Covers the HTTP callback capture (core/action_url.py) using real localhost
GET requests, plus the ALE-700A provider verification that waits for the
phone's Action URL event instead of only confirming command acceptance.
"""
from urllib.request import ProxyHandler, build_opener

from core.models import TestCase
from oem.ale700a import ActionUrlListener, Ale700aProvider, resolve_event_name

# Bypass any ambient HTTP proxy so localhost requests reach the test server.
_opener = build_opener(ProxyHandler({}))


def _case():
    return TestCase(id="TC_CALL_001", name="basic_call", description="", required_capabilities=["basic_call"])


def _get(url):
    with _opener.open(url, timeout=2) as resp:  # noqa: S310 - localhost test server
        return resp.status, resp.read()


def test_resolve_event_name_prefers_query_param():
    assert resolve_event_name("/action", {"event": "call_established"}) == "call_established"


def test_resolve_event_name_falls_back_to_path_segment():
    assert resolve_event_name("/call_terminated.xml", {}) == "call_terminated"


def test_listener_records_callback_from_real_http_get():
    with ActionUrlListener() as listener:
        status, body = _get(f"{listener.url}/action?event=setup_completed&mac=00a859ebf35b&ip=10.10.6.141")

        assert status == 200
        assert body == b"OK"
        events = listener.events
        assert len(events) == 1
        assert events[0].event == "setup_completed"
        assert events[0].params["mac"] == "00a859ebf35b"


def test_wait_for_event_returns_matching_event():
    with ActionUrlListener() as listener:
        _get(f"{listener.url}/action?event=call_established&cid=3")

        received = listener.wait_for_event("call_established", timeout=2)

        assert received is not None
        assert received.params["cid"] == "3"


def test_wait_for_event_times_out_when_absent():
    with ActionUrlListener() as listener:
        assert listener.wait_for_event("call_established", timeout=0.2) is None


def test_wait_for_event_consumes_so_each_event_matches_once():
    with ActionUrlListener() as listener:
        _get(f"{listener.url}/action?event=call_established")

        assert listener.wait_for_event("call_established", timeout=1) is not None
        # The same event is not matched again.
        assert listener.wait_for_event("call_established", timeout=0.2) is None


def test_wait_for_event_honours_match_filter():
    with ActionUrlListener() as listener:
        _get(f"{listener.url}/action?event=call_established&cid=9")

        assert listener.wait_for_event("call_established", timeout=0.3, match={"cid": "1"}) is None
        assert listener.wait_for_event("call_established", timeout=1, match={"cid": "9"}) is not None


def test_provider_verification_passes_when_event_arrives():
    with ActionUrlListener() as listener:
        provider = Ale700aProvider(listener=listener)
        _get(f"{listener.url}/action?event=call_established&cid=3")

        ok, detail = provider.run_step(
            _case(), {"kind": "VERIFICATION", "name": "verify.call_connected", "timeout": 2}
        )

        assert ok is True
        assert detail["expected_event"] == "call_established"
        assert detail["event_params"]["cid"] == "3"


def test_provider_verification_fails_on_timeout():
    with ActionUrlListener() as listener:
        provider = Ale700aProvider(listener=listener)

        ok, detail = provider.run_step(
            _case(), {"kind": "VERIFICATION", "name": "verify.call_connected", "timeout": 0.2}
        )

        assert ok is False
        assert "timed out" in detail["message"]


def test_provider_without_listener_stays_accepted():
    # Backward-compatible: no listener -> command-acceptance verification.
    provider = Ale700aProvider()

    ok, detail = provider.run_step(
        _case(), {"kind": "VERIFICATION", "name": "verify.call_connected", "timeout": 1}
    )

    assert ok is True
    assert "accepted via Active URI" in detail["message"]
