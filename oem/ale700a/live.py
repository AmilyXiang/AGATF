"""ALE-700A live-provider builder (Provider-layer HOW for run --live).

Moved out of the CLI so the vendor-neutral entry point holds no ALE-700A
specifics (slide12 / slide13 / slide16 decision 4). The CLI reaches this only
through the provider registry, keyed by operation_mode 'active_uri'.
"""
from __future__ import annotations

import logging

from core.provider_registry import LiveProvider
from oem.ale700a.action_url import ActionUrlListener
from oem.ale700a.provider import ActiveUriClient, Ale700aProvider

logger = logging.getLogger(__name__)


def build_live_provider(device_data: dict, lab_data: dict, options: dict) -> LiveProvider:
    """Construct the real ALE-700A provider + Action URL listener from config.

    The controlled DUT is chosen by ``options['dut']`` (the --dut id); without
    it the first DUT in the lab is used. Reach/credential details come from that
    DUT instance (ip + its ``control`` block), not from the device profile.
    """
    duts = lab_data.get("duts", lab_data.get("instances", []))
    dut_id = options.get("dut")
    if dut_id:
        dut = next((d for d in duts if d.get("id") == dut_id), None)
        if dut is None:
            raise ValueError(f"--dut '{dut_id}' not found in lab config")
    elif duts:
        dut = duts[0]
    else:
        raise ValueError("run --live requires at least one DUT in the lab config")

    control = dut.get("control", {})
    ip = dut["ip"]
    protocol = control.get("protocol", "http")
    port = control.get("port")
    base_url = f"{protocol}://{ip}" + (f":{port}" if port else "")
    verify_tls = control.get("verify_tls", True) and not options.get("insecure", False)

    au = lab_data.get("action_url", {})
    listener = ActionUrlListener(
        host=au.get("host", "0.0.0.0"),
        port=au.get("port", 8080),
        on_event=lambda e: logger.info("[action-url] %s %s", e.event, e.params),
    ).start()
    print(f"Action URL listener on {listener.url}")
    print(f"Controlling DUT {dut.get('id')} at {base_url}")

    client = ActiveUriClient(
        base_url,
        username=control.get("username", "admin"),
        password=lab_data.get("password"),
        secret_ref=lab_data.get("secret_ref"),
        verify_tls=verify_tls,
    )
    provider = Ale700aProvider(client=client, listener=listener, default_number=options.get("number") or "")
    # DUT id -> phone number, so dial/transfer targets come from bindings.
    dut_numbers = {d["id"]: d.get("number", "") for d in duts}
    return LiveProvider(provider=provider, dut_numbers=dut_numbers, teardown=listener.stop)
