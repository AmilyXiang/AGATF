from core.models import DUTInstance, DUTPool, TestCase
from core.provider import ApiStubProvider, PhysicalStubProvider, StubProvider
from core.resolver import Resolver


def _hold_case():
    # The SAME Case object is reused for both backends; it is never mutated.
    return TestCase(
        id="COMMON_HOLD_001",
        name="hold_resume",
        description="",
        required_capabilities=["hold", "resume"],
    )


def _pool():
    return DUTPool(
        [DUTInstance(id="dut_01", profile="P")],
        {"P": {"hold", "resume"}},
    )


def test_same_case_binds_physical_provider_in_physical_mode():
    resolver = Resolver([ApiStubProvider(), PhysicalStubProvider(), StubProvider()])
    case = _hold_case()

    plan = resolver.build_plan("P", "SIP", "OXE", {"hold", "resume"}, [case], _pool(), operation_mode="physical")

    assert plan.items[0].provider == "physical_provider"


def test_same_case_binds_api_provider_in_api_mode():
    resolver = Resolver([ApiStubProvider(), PhysicalStubProvider(), StubProvider()])
    case = _hold_case()

    plan = resolver.build_plan("P", "SIP", "OXE", {"hold", "resume"}, [case], _pool(), operation_mode="api")

    assert plan.items[0].provider == "api_provider"


def test_case_is_identical_across_backends():
    resolver = Resolver([ApiStubProvider(), PhysicalStubProvider(), StubProvider()])
    case = _hold_case()

    api_plan = resolver.build_plan("P", "SIP", "OXE", {"hold", "resume"}, [case], _pool(), operation_mode="api")
    phys_plan = resolver.build_plan("P", "SIP", "OXE", {"hold", "resume"}, [case], _pool(), operation_mode="physical")

    # Providers differ, but the compiled abstract steps are the same Case.
    assert api_plan.items[0].provider != phys_plan.items[0].provider
    api_steps = [(s.kind, s.name) for s in api_plan.items[0].compiled_steps]
    phys_steps = [(s.kind, s.name) for s in phys_plan.items[0].compiled_steps]
    assert api_steps == phys_steps
