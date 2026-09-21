"""Case Parser / Compiler from business intent to abstract atomic steps.

Compiles a Case's business-facing steps into ordered abstract Atomic Steps,
split into ACTION and VERIFICATION (e.g. {action: hold, expected: hold} ->
phone.hold + verify.call_on_hold). The output is intentionally OEM-agnostic:
it contains no SSH command, REST endpoint, Robot coordinate, or Camera model.
Unknown actions/verifications raise ValueError so bad Cases fail fast.

Used by: resolver (writes compiled_steps into the Test Plan) and executor
(runs these abstract steps instead of reading Case action/expected directly).
"""
from __future__ import annotations

import logging

from core.models import AtomicStep, CaseStep, TestCase

logger = logging.getLogger(__name__)


_ACTION_NAMES = {
    "dial": "phone.dial",
    "answer": "phone.answer",
    "hold": "phone.hold",
    "resume": "phone.resume",
    "transfer": "phone.transfer",
    "reboot": "device.reboot",
}

_EXPECTATION_NAMES = {
    "connected": "verify.call_connected",
    "hold": "verify.call_on_hold",
    "registered": "verify.registered",
    "initialized": "verify.initialized",
}


def compile_step(step: CaseStep) -> list[AtomicStep]:
    """Compile one legacy CaseStep into an action and optional verification."""
    action_name = _ACTION_NAMES.get(step.action)
    expected_name = _EXPECTATION_NAMES.get(step.expected)
    if action_name is None:
        logger.error("unknown abstract action '%s'", step.action)
        raise ValueError(f"Unknown abstract action '{step.action}'")
    if expected_name is None:
        logger.error("unknown abstract verification '%s'", step.expected)
        raise ValueError(f"Unknown abstract verification '{step.expected}'")

    return [
        AtomicStep(kind="ACTION", name=action_name, timeout=step.timeout),
        AtomicStep(kind="VERIFICATION", name=expected_name, timeout=step.timeout),
    ]


def compile_case(case: TestCase) -> list[AtomicStep]:
    """Compile all steps in order; OEM-specific HOW is intentionally absent."""
    compiled: list[AtomicStep] = []
    for step in case.steps:
        compiled.extend(compile_step(step))
    logger.debug("compiled case %s into %d atomic steps", case.id, len(compiled))
    return compiled
