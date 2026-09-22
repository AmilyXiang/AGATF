"""Tests for the ALE-700A Active URI provider (core/ale700a.py).

Verifies the abstract atomic step -> Active URI key mapping and the HTTP GET
URL construction against the doc, using an injected fake sender so no real
phone is required. Also checks provider binding under operation_mode.
"""
from core.models import DUTInstance, DUTPool, TestCase
from core.resolver import Resolver
from oem.ale700a import ACTIVE_URI_PATH, ActiveUriClient, Ale700aProvider


def _case():
    return TestCase(id="TC_CALL_001", name="basic_call", description="", required_capabilities=["basic_call"])


class _RecordingSender:
    """Fake sender capturing every URL and returning a canned status."""

    def __init__(self, status=200):
        self.status = status
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        return 200 <= self.status < 300, self.status


def test_dial_maps_to_speaker_number_enter():
    sender = _RecordingSender()
    provider = Ale700aProvider(ActiveUriClient("http://10.10.6.141", sender=sender), default_number="2001")

    ok, detail = provider.run_step(_case(), {"kind": "ACTION", "name": "phone.dial", "timeout": 30})

    assert ok is True
    assert detail["url"] == f"http://10.10.6.141{ACTIVE_URI_PATH}?key=SPEAKER;2001;ENTER"
    assert sender.calls[0][0] == detail["url"]


def test_hold_maps_to_f_hold_key():
    sender = _RecordingSender()
    provider = Ale700aProvider(ActiveUriClient("http://10.10.6.141", sender=sender))

    ok, detail = provider.run_step(_case(), {"kind": "ACTION", "name": "phone.hold", "timeout": 30})

    assert ok is True
    assert detail["url"].endswith("?key=F_HOLD")


def test_transfer_maps_to_f_transfer_number_ok():
    sender = _RecordingSender()
    provider = Ale700aProvider(ActiveUriClient("http://10.10.6.141", sender=sender), default_number="0000")

    _, detail = provider.run_step(_case(), {"kind": "ACTION", "name": "phone.transfer", "timeout": 30})

    assert detail["url"].endswith("?key=F_TRANSFER;0000;OK")


def test_unknown_action_fails_fast():
    provider = Ale700aProvider(ActiveUriClient("http://10.10.6.141", sender=_RecordingSender()))

    ok, detail = provider.run_step(_case(), {"kind": "ACTION", "name": "phone.levitate", "timeout": 30})

    assert ok is False
    assert "unsupported" in detail["error"]


def test_verification_step_is_accepted_without_network():
    sender = _RecordingSender()
    provider = Ale700aProvider(ActiveUriClient("http://10.10.6.141", sender=sender))

    ok, detail = provider.run_step(_case(), {"kind": "VERIFICATION", "name": "verify.call_connected", "timeout": 30})

    assert ok is True
    assert sender.calls == []  # verification sends nothing in the basic HOW


def test_dry_run_records_url_without_sending():
    # No base_url and no sender => dry-run mode, safe to run without a phone.
    provider = Ale700aProvider(default_number="3001")

    ok, detail = provider.run_step(_case(), {"kind": "ACTION", "name": "phone.dial", "timeout": 30})

    assert ok is True
    assert detail["mode"] == "dry-run"
    assert detail["key"] == "SPEAKER;3001;ENTER"


def test_http_status_error_marks_step_failed():
    sender = _RecordingSender(status=401)
    provider = Ale700aProvider(ActiveUriClient("http://10.10.6.141", sender=sender))

    ok, detail = provider.run_step(_case(), {"kind": "ACTION", "name": "phone.answer", "timeout": 30})

    assert ok is False
    assert detail["http_status"] == 401


def test_provider_binds_in_active_uri_mode():
    pool = DUTPool([DUTInstance(id="dut_01", profile="ALE700A")], {"ALE700A": {"basic_call"}})
    resolver = Resolver([Ale700aProvider()])

    plan = resolver.build_plan(
        "ALE700A", "SIP", "OXE", {"basic_call"}, [_case()], pool, operation_mode="active_uri"
    )

    assert plan.items[0].provider == "ale700a_active_uri"
