import pytest

from core.compiler import compile_case
from core.models import CaseStep, TestCase


def test_compile_hold_case_to_action_and_verification():
    case = TestCase(
        id="HOLD",
        name="hold",
        description="",
        steps=[CaseStep(action="hold", expected="hold", timeout=20)],
    )

    steps = compile_case(case)

    assert [(step.kind, step.name, step.timeout) for step in steps] == [
        ("ACTION", "phone.hold", 20),
        ("VERIFICATION", "verify.call_on_hold", 20),
    ]


def test_compile_rejects_unknown_abstract_action():
    case = TestCase(
        id="INVALID",
        name="invalid",
        description="",
        steps=[CaseStep(action="ssh_command", expected="connected")],
    )

    with pytest.raises(ValueError, match="Unknown abstract action"):
        compile_case(case)
