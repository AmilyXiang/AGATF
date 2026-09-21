"""Executor layer (slide12 EXECUTOR): runs steps in order and records evidence.

For each PlanItem it resolves the bound provider, runs the case's abstract
Atomic Steps in order (compiled_steps, e.g. phone.hold / verify.call_on_hold),
and aggregates one Evidence per case. A case is 'pass' only when every step
and the provider's finalize both pass; any failed step fails the case.

The executor owns sequence / timeout / verdict only. It runs abstract steps
(step.kind / step.name) and never interprets Case action/expected or contains
OEM behaviour; that HOW lives entirely in the provider layer.
"""
from __future__ import annotations

import logging

from core.compiler import compile_case
from core.models import Evidence, ExecutionResult, TestPlan
from core.reservation import ResourceManager

logger = logging.getLogger(__name__)


class Executor:
    """Runs all plan items using the provider selected during resolution."""

    def __init__(self, providers_by_name: dict[str, object]) -> None:
        self.providers_by_name = providers_by_name
        # Owns resource Reserve (step 7) and Release (step 10) during a run.
        self.resources = ResourceManager()

    def run_plan(self, plan: TestPlan) -> ExecutionResult:
        evidences: list[Evidence] = []
        logger.info("run_plan %s: %d items", plan.plan_id, len(plan.items))

        for item in plan.items:
            provider = self.providers_by_name[item.provider]
            case = item.case
            case_ok = True
            details: dict[str, object] = {"provider": item.provider, "steps": []}

            # Step 7: reserve the DUTs and bench resources this case is bound to,
            # so a concurrent run cannot use them; released in the finally block.
            reserved_ids = list(item.role_bindings.values()) + list(item.resource_bindings.values())
            self.resources.reserve(reserved_ids)
            details["reserved_resources"] = reserved_ids
            logger.info("case %s: provider=%s reserved=%s", case.id, item.provider, reserved_ids)
            try:
                steps = item.compiled_steps or compile_case(case)
                for step in steps:
                    ok, step_data = provider.run_step(
                        case,
                        {"kind": step.kind, "name": step.name, "timeout": step.timeout},
                    )
                    details["steps"].append(step_data)
                    if not ok:
                        logger.warning("case %s step %s failed", case.id, step.name)
                    # One failed step fails the whole case.
                    case_ok = case_ok and ok

                final_data = provider.finalize(case)
            finally:
                # Step 10: cleanup & release so later cases can reuse the DUTs.
                self.resources.release(reserved_ids)
                logger.debug("case %s: released %s", case.id, reserved_ids)

            verdict = "pass" if case_ok and final_data.get("status") == "pass" else "fail"
            logger.info("case %s verdict=%s", case.id, verdict)

            evidences.append(
                Evidence(
                    case_id=case.id,
                    case_name=case.name,
                    status=verdict,
                    provider=item.provider,
                    details={**details, **final_data},
                )
            )

        return ExecutionResult(plan_id=plan.plan_id, evidences=evidences)
