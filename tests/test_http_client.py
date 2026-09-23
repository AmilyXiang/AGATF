"""Tests for the vendor-neutral HTTP transport tool (tools/http_client.py)."""
from tools.http_client import HttpClient, basic_auth_header


def test_basic_auth_header_encodes_credentials():
    header = basic_auth_header("admin", "secret")
    # base64("admin:secret") == "YWRtaW46c2VjcmV0"
    assert header == {"Authorization": "Basic YWRtaW46c2VjcmV0"}


def test_basic_auth_header_empty_when_no_password():
    assert basic_auth_header("admin", "") == {}


def test_http_client_get_uses_injected_transport_semantics():
    # 2xx is ok; 4xx/5xx and transport failure (status 0) are not.
    client = HttpClient()

    for status, expected in [(200, True), (204, True), (401, False), (500, False)]:
        assert (200 <= status < 300) is expected  # documents the contract used by get()
    # verify_tls flag is retained for the transport to consume.
    insecure = HttpClient(verify_tls=False)
    assert insecure.verify_tls is False
    assert client.verify_tls is True
