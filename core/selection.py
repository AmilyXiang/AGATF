"""Case selection: derive Applicable Cases from Runtime Context.

Evaluates each Case against the current RuntimeContext and assigns one of four
statuses (slide6):
- CONFIG_ERROR: Case missing id / name / steps.
- NOT_APPLICABLE: scope / protocol / capability / operation_mode mismatch.
- BLOCKED_RESOURCE: DUT count too low, role capabilities unmet, or lab
  resources missing.
- READY: all constraints satisfied; resource bindings attached, enters plan.

Checks run cheap-to-expensive and short-circuit on the first failure:
config -> scope -> protocol -> capability -> operation_mode -> DUT count ->
role capabilities -> lab resources -> READY.

Pipeline: selection (this file) -> resolver -> executor.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging

from core.binder import bind_resources
from core.models import RuntimeContext, SelectionStatus, TestCase

logger = logging.getLogger(__name__)


@dataclass
class SelectionOutcome:
    case: TestCase
    status: SelectionStatus
    reason: str
    resource_bindings: dict[str, str] | None = None

    @property
    def applicable(self) -> bool:
        """Keep the P0 boolean API while exposing the v2 status."""
        return self.status == SelectionStatus.READY


def evaluate_case(case: TestCase, context: RuntimeContext, scope: str | None = None) -> SelectionOutcome:
    device = context.device

    if not case.id or not case.name or not case.steps:
        return SelectionOutcome(case, SelectionStatus.CONFIG_ERROR, "case id, name, and steps are required")

    if scope is not None and case.scope != scope:
        return SelectionOutcome(case, SelectionStatus.NOT_APPLICABLE, f"scope '{case.scope}' != requested '{scope}'")

    if case.protocols and device.protocol not in case.protocols:
        return SelectionOutcome(case, SelectionStatus.NOT_APPLICABLE, f"protocol '{device.protocol}' not in {case.protocols}")

    required_caps = set(case.required_capabilities)
    available_caps = set(device.capabilities)
    missing_caps = required_caps - available_caps
    if missing_caps:
        return SelectionOutcome(case, SelectionStatus.NOT_APPLICABLE, f"missing capabilities {sorted(missing_caps)}")

    if case.operation_modes and device.operation_mode not in case.operation_modes:
        return SelectionOutcome(case, SelectionStatus.NOT_APPLICABLE, f"operation_mode '{device.operation_mode}' not in {case.operation_modes}")

    if len(case.required_dut_roles) > len(context.dut_pool.instances):
        return SelectionOutcome(
            case,
            SelectionStatus.BLOCKED_RESOURCE,
            f"DUT Pool has {len(context.dut_pool.instances)} instances but requires {len(case.required_dut_roles)} roles",
            {},
        )

    used_instances: set[str] = set()
    for role in case.required_dut_roles:
        required_role_caps = set(case.role_capabilities.get(role, []))
        selected_instance = next(
            (
                instance
                for instance in context.dut_pool.instances
                if instance.id not in used_instances
                and required_role_caps.issubset(
                    context.dut_pool.profile_capabilities.get(instance.profile, set())
                )
            ),
            None,
        )
        if selected_instance is None:
            return SelectionOutcome(
                case,
                SelectionStatus.BLOCKED_RESOURCE,
                f"no DUT instance can satisfy role '{role}' capabilities {sorted(required_role_caps)}",
                {},
            )
        used_instances.add(selected_instance.id)

    resource_bindings, missing_resources = bind_resources(case, context)
    if missing_resources:
        return SelectionOutcome(case, SelectionStatus.BLOCKED_RESOURCE, f"missing resources {sorted(missing_resources)}", {})

    return SelectionOutcome(case, SelectionStatus.READY, "ready", resource_bindings)


def filter_applicable_cases(
    cases: list[TestCase], context: RuntimeContext, scope: str | None = None
) -> tuple[list[TestCase], list[SelectionOutcome]]:
    logger.debug("filter_applicable_cases: %d cases, scope=%s", len(cases), scope)
    outcomes = [evaluate_case(case, context, scope) for case in cases]
    for outcome in outcomes:
        logger.debug("case %s -> %s (%s)", outcome.case.id, outcome.status.value, outcome.reason)
    applicable = [o.case for o in outcomes if o.applicable]
    logger.info("selection: %d/%d cases READY", len(applicable), len(cases))
    return applicable, outcomes
