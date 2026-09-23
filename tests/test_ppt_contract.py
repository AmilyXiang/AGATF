import json
from pathlib import Path

from cli import build_runtime_context, generate_plan, parse_cases
from core.provider import StubProvider
from core.resolver import Resolver


def test_plan_contract_keeps_case_steps(tmp_path):
    device_data = {
        "name": "OEM_PHONE_A",
        "protocol": "SIP",
        "platform": "OXE",
        "capabilities": ["basic_call", "hold", "resume", "transfer", "audio"],
        "operation_mode": "physical",
        "firmware": "R510",
        "ip": "10.10.10.21",
    }
    lab_data = {
        "name": "lab_sh_01",
        "host": "10.10.10.10",
        "secret_ref": "lab/deskphone/test-secret",
        "resources": {"camera": "cam-01"},
    }
    case_data = [
        {
            "id": "TC_CALL_001",
            "name": "basic_call",
            "description": "Place a basic call and end it cleanly.",
            "required_capabilities": ["basic_call"],
            "steps": [
                {"action": "dial", "expected": "connected", "timeout": 30},
                {"action": "answer", "expected": "connected", "timeout": 30},
            ],
        }
    ]

    class Args:
        device = "tests/fixtures/device.json"
        lab = "tests/fixtures/lab.json"
        cases = "cases/common.json"
        output = str(tmp_path / "plan.json")

    context = build_runtime_context(device_data, lab_data)
    provider = StubProvider()
    resolver = Resolver([provider])
    case_objs = parse_cases(case_data)

    plan = resolver.build_plan(
        context.device.name,
        context.device.protocol,
        context.device.platform,
        set(context.device.capabilities),
        case_objs,
    )

    assert plan.items[0].case.steps[0].action == "dial"

    args = Args()
    generate_plan(args)
    saved = json.loads(Path(args.output).read_text(encoding="utf-8"))

    assert saved["items"][0]["case"]["id"] == "TC_CALL_001"
    assert saved["items"][0]["case"]["steps"][0]["action"] == "dial"
    assert saved["items"][0]["compiled_steps"] == [
        {"kind": "ACTION", "name": "phone.dial", "timeout": 30},
        {"kind": "VERIFICATION", "name": "verify.call_connected", "timeout": 30},
        {"kind": "ACTION", "name": "phone.answer", "timeout": 30},
        {"kind": "VERIFICATION", "name": "verify.call_connected", "timeout": 30},
    ]
