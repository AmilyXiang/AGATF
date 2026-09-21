"""Resolver layer (slide12 RESOLVER): decides WHO implements each case.

For every applicable Case it performs three bindings and assembles them into
an immutable Test Plan:
- Provider binding: pick a provider whose capabilities satisfy the Case.
- DUT Role binding: map logical roles (caller/callee) to distinct real DUT
  instances from the DUT Pool.
- Atomic Step compilation: compile the Case into abstract steps.

Fail fast: if no provider fits or the DUT Pool is insufficient, it raises
immediately so binding problems surface before execution. It never runs steps
(executor's job) and holds no OEM-specific HOW (provider's job).

Pipeline: selection -> resolver (this file) -> executor.
"""
from __future__ import annotations

import logging

from core.compiler import compile_case
from core.models import DUTPool, PlanItem, TestCase, TestPlan
from core.provider import BaseProvider, StubProvider

logger = logging.getLogger(__name__)


class Resolver:
    """Selects the right provider for a case and config combination."""

    def __init__(self, providers: list[BaseProvider] | None = None) -> None:
        self.providers = providers or [StubProvider()]

    def select_provider(self, case: TestCase, config_capabilities: set[str], operation_mode: str | None = None) -> BaseProvider:
        # Fail fast: an unbindable case is a config/binding error, surfaced
        # before execution rather than during it. When operation_mode is given,
        # the provider's backend must match (slide11 API vs Physical).
        for provider in self.providers:
            if not provider.supports_case(case, config_capabilities):
                continue
            if operation_mode is not None and not provider.supports_backend(operation_mode):
                continue
            logger.debug("case %s -> provider %s (mode=%s)", case.id, provider.name, operation_mode)
            return provider
        logger.error("no provider for case %s caps=%s mode=%s", case.id, case.required_capabilities, operation_mode)
        raise ValueError(f"No provider can satisfy case '{case.id}' for required capabilities {case.required_capabilities}")

    def bind_roles(self, case: TestCase, dut_pool: DUTPool) -> dict[str, str]:
        """Bind logical Case roles to distinct real DUT instances."""
        bindings: dict[str, str] = {}
        used: set[str] = set()
        for role in case.required_dut_roles:
            required = set(case.role_capabilities.get(role, []))
            selected = next(
                (
                    instance
                    for instance in dut_pool.instances
                    if instance.id not in used
                    and required.issubset(dut_pool.profile_capabilities.get(instance.profile, set()))
                ),
                None,
            )
            if selected is None:
                raise ValueError(
                    f"Insufficient DUT Pool for case '{case.id}' role '{role}' "
                    f"with capabilities {sorted(required)}"
                )
            bindings[role] = selected.id
            used.add(selected.id)
        logger.debug("case %s role bindings: %s", case.id, bindings)
        return bindings

    def build_plan(
        self,
        device_name: str,
        protocol: str,
        platform: str,
        config_capabilities: set[str],
        cases: list[TestCase],
        dut_pool: DUTPool | None = None,
        resource_bindings_by_case: dict[str, dict[str, str]] | None = None,
        operation_mode: str | None = None,
    ) -> TestPlan:
        pool = dut_pool or DUTPool([])
        resource_bindings_by_case = resource_bindings_by_case or {}
        logger.info("build_plan: %d cases, %d DUTs, mode=%s", len(cases), len(pool.instances), operation_mode)
        items: list[PlanItem] = []
        for case in cases:
            provider = self.select_provider(case, config_capabilities, operation_mode)
            role_bindings = self.bind_roles(case, pool)
            items.append(
                PlanItem(
                    case=case,
                    provider=provider.name,
                    selected_capabilities=[cap for cap in case.required_capabilities],
                    role_bindings=role_bindings,
                    resource_bindings=resource_bindings_by_case.get(case.id, {}),
                    compiled_steps=compile_case(case),
                )
            )

        return TestPlan(
            plan_id=f"plan-{device_name}-{protocol}-{platform}",
            device=device_name,
            protocol=protocol,
            platform=platform,
            items=items,
            dut_pool=[instance.id for instance in pool.instances],
        )
