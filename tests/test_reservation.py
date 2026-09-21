import pytest

from core.executor import Executor
from core.models import AtomicStep, Evidence, PlanItem, TestCase, TestPlan
from core.provider import StubProvider
from core.reservation import ReservationError, ResourceManager


def test_reserve_conflict_raises():
    manager = ResourceManager()
    manager.reserve(["dut_01", "mic-02"])
    with pytest.raises(ReservationError, match="dut_01"):
        manager.reserve(["dut_01"])


def test_release_allows_reuse():
    manager = ResourceManager()
    manager.reserve(["dut_01"])
    manager.release(["dut_01"])
    manager.reserve(["dut_01"])
    assert manager.locked == {"dut_01"}


def test_reserved_context_manager_releases_on_exit():
    manager = ResourceManager()
    with manager.reserved(["robot-07"]):
        assert manager.locked == {"robot-07"}
    assert manager.locked == set()


def _plan_with_one_case():
    case = TestCase(
        id="CALL",
        name="basic_call",
        description="",
        required_capabilities=["basic_call"],
        steps=[],
    )
    item = PlanItem(
        case=case,
        provider="stub_provider",
        selected_capabilities=["basic_call"],
        role_bindings={"caller": "dut_01", "callee": "dut_02"},
        resource_bindings={"audio": "mic-02"},
        compiled_steps=[AtomicStep(kind="ACTION", name="phone.dial", timeout=30)],
    )
    return TestPlan(plan_id="p", device="d", protocol="SIP", platform="OXE", items=[item])


def test_executor_reserves_and_releases_resources():
    executor = Executor({"stub_provider": StubProvider()})
    result = executor.run_plan(_plan_with_one_case())

    # After the run every resource is released again.
    assert executor.resources.locked == set()
    assert result.evidences[0].details["reserved_resources"] == ["dut_01", "dut_02", "mic-02"]
