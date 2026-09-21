# Unit tests for the slide5 Filter dimensions plus an end-to-end plan check.
import json
from pathlib import Path

from cli import generate_plan
from core.models import CaseStep, DUTInstance, DeviceConfig, LabConfig, RuntimeContext, SelectionStatus, TestCase
from core.selection import filter_applicable_cases


def make_context(protocol="SIP", operation_mode="physical", capabilities=None, resources=None):
    device = DeviceConfig(
        name="DUT",
        protocol=protocol,
        platform="OXE",
        capabilities=capabilities or ["basic_call", "hold", "resume", "audio"],
        operation_mode=operation_mode,
    )
    lab = LabConfig(name="lab", host="10.0.0.1", resources=resources or {"audio": "mic-02"})
    return RuntimeContext(device=device, lab=lab, resources=resources or {"audio": "mic-02"})


def case(cid, **kwargs):
    kwargs.setdefault("steps", [CaseStep(action="noop", expected="done")])
    return TestCase(id=cid, name=cid, description="", **kwargs)


def test_capability_filter_skips_missing_capability():
    ctx = make_context(capabilities=["basic_call"])
    cases = [case("A", required_capabilities=["basic_call"]), case("B", required_capabilities=["transfer"])]
    applicable, outcomes = filter_applicable_cases(cases, ctx)
    assert [c.id for c in applicable] == ["A"]
    assert any(not o.applicable and "transfer" in o.reason for o in outcomes)


def test_protocol_filter_skips_other_protocol():
    ctx = make_context(protocol="SIP")
    cases = [case("SIP1", protocols=["SIP"]), case("NOE1", protocols=["NOE"])]
    applicable, _ = filter_applicable_cases(cases, ctx)
    assert [c.id for c in applicable] == ["SIP1"]


def test_resource_filter_skips_missing_resource():
    ctx = make_context(resources={"camera": "cam-01"})
    cases = [case("R1", required_resources=["audio"])]
    applicable, outcomes = filter_applicable_cases(cases, ctx)
    assert applicable == []
    assert "audio" in outcomes[0].reason


def test_operation_mode_filter():
    ctx = make_context(operation_mode="api")
    cases = [case("M1", operation_modes=["physical"])]
    applicable, _ = filter_applicable_cases(cases, ctx)
    assert applicable == []


def test_scope_filter():
    ctx = make_context()
    cases = [case("C1", scope="common"), case("S1", scope="sip")]
    applicable, _ = filter_applicable_cases(cases, ctx, scope="sip")
    assert [c.id for c in applicable] == ["S1"]


def test_empty_constraints_are_applicable_to_any():
    ctx = make_context(protocol="NOE")
    cases = [case("ANY", required_capabilities=["basic_call"])]
    applicable, _ = filter_applicable_cases(cases, ctx)
    assert [c.id for c in applicable] == ["ANY"]


def test_generated_plan_excludes_non_matching_protocol(tmp_path):
    # End-to-end: a SIP device must not produce a plan containing NOE-only cases.
    class Args:
        device = "config/device.json"
        lab = "config/lab.json"
        cases = "cases/common.json"
        output = str(tmp_path / "plan.json")
        scope = None

    generate_plan(Args())
    plan = json.loads(Path(Args.output).read_text(encoding="utf-8"))

    case_ids = [item["case"]["id"] for item in plan["items"]]
    assert "TC_NOE_INIT_001" not in case_ids
    assert "TC_SIP_REG_001" in case_ids

    audio_item = next(item for item in plan["items"] if item["case"]["id"] == "TC_AUDIO_001")
    assert audio_item["resource_bindings"] == {"audio": "mic-02"}


def test_missing_lab_resource_is_blocked_resource():
    ctx = make_context(resources={"camera": "cam-01"})
    audio_case = case(
        "AUDIO",
        required_capabilities=["basic_call"],
        required_resources=["audio"],
        steps=[CaseStep(action="dial", expected="connected")],
    )
    _, outcomes = filter_applicable_cases([audio_case], ctx)
    assert outcomes[0].status == SelectionStatus.BLOCKED_RESOURCE
    assert outcomes[0].resource_bindings == {}


def test_role_capability_shortage_is_blocked_resource():
    ctx = make_context()
    ctx.dut_pool.instances = [DUTInstance(id="dut_01", profile="DUT")]
    ctx.dut_pool.profile_capabilities = {"DUT": {"basic_call"}}
    ctx.dut_pool.instances[0].profile = "DUT"
    role_case = case(
        "ROLE",
        required_dut_roles=["caller"],
        role_capabilities={"caller": ["audio"]},
    )
    _, outcomes = filter_applicable_cases([role_case], ctx)
    assert outcomes[0].status == SelectionStatus.BLOCKED_RESOURCE


def test_protocol_mismatch_is_not_applicable():
    ctx = make_context(protocol="SIP")
    noe_case = case(
        "NOE",
        protocols=["NOE"],
        steps=[CaseStep(action="reboot", expected="initialized")],
    )
    _, outcomes = filter_applicable_cases([noe_case], ctx)
    assert outcomes[0].status == SelectionStatus.NOT_APPLICABLE


def test_missing_case_steps_is_config_error():
    ctx = make_context()
    invalid_case = TestCase(id="INVALID", name="INVALID", description="")
    _, outcomes = filter_applicable_cases([invalid_case], ctx)
    assert outcomes[0].status == SelectionStatus.CONFIG_ERROR
