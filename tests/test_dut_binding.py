import json
from pathlib import Path

from cli import generate_plan
from core.models import DUTInstance, DUTPool, TestCase
from core.resolver import Resolver
from core.provider import StubProvider


def test_resolver_binds_logical_roles_to_distinct_duts():
    resolver = Resolver([StubProvider()])
    case = TestCase(
        id="CALL",
        name="basic_call",
        description="",
        required_capabilities=["basic_call"],
        required_dut_roles=["caller", "callee"],
    )
    pool = DUTPool([
        DUTInstance(id="dut_01", profile="OEM_PHONE_A"),
        DUTInstance(id="dut_02", profile="OEM_PHONE_A"),
    ], {"OEM_PHONE_A": {"basic_call"}})

    plan = resolver.build_plan("OEM_PHONE_A", "SIP", "OXE", {"basic_call"}, [case], pool)

    bindings = plan.items[0].role_bindings
    assert set(bindings) == {"caller", "callee"}
    assert bindings["caller"] != bindings["callee"]
    assert plan.dut_pool == ["dut_01", "dut_02"]


def test_generated_plan_contains_role_bindings(tmp_path):
    class Args:
        device = "config/device.json"
        lab = "config/lab.json"
        cases = "cases/common.json"
        output = str(tmp_path / "plan.json")
        scope = "common"

    generate_plan(Args())
    plan = json.loads(Path(Args.output).read_text(encoding="utf-8"))

    call_item = next(item for item in plan["items"] if item["case"]["id"] == "TC_CALL_001")
    audio_item = next(item for item in plan["items"] if item["case"]["id"] == "TC_AUDIO_001")
    assert plan["dut_pool"] == ["dut_01", "dut_02"]
    assert set(call_item["role_bindings"]) == {"caller", "callee"}
    assert call_item["role_bindings"]["caller"] != call_item["role_bindings"]["callee"]
    assert set(audio_item["role_bindings"]) == {"caller", "callee"}
    assert audio_item["role_bindings"]["caller"] != audio_item["role_bindings"]["callee"]
