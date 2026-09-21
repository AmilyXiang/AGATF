"""core data structures for the CLI-first DeskPhone automation framework.

These dataclasses form the execution contract described in the PPT:
Config/Context -> Case (WHAT) -> Test Plan -> Evidence. They carry no
OEM-specific behaviour; the HOW lives in providers.

Grouped by the data chain:
- Config / Context: Capability, DeviceProfile (alias DeviceConfig),
  DUTInstance, DUTPool, LabConfig, RuntimeContext.
- Case (WHAT): CaseStep (business step), AtomicStep (compiled ACTION /
  VERIFICATION), TestCase (intent + filter metadata).
- Selection status: SelectionStatus (READY / NOT_APPLICABLE /
  BLOCKED_RESOURCE / CONFIG_ERROR).
- Test Plan (execution contract): PlanItem, TestPlan.
- Result: Evidence (per case), ExecutionResult (whole plan).

This is the shared vocabulary every other module (selection / binder /
compiler / resolver / executor / cli) passes data through.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Capability(str, Enum):
    """Vocabulary of device capabilities used for case filtering and binding."""

    BASIC_CALL = "basic_call"
    HOLD = "hold"
    RESUME = "resume"
    TRANSFER = "transfer"
    AUDIO = "audio"
    TLS = "tls"
    MWI = "mwi"


class SelectionStatus(str, Enum):
    """Preparation status required by the v2 Case Selection design."""

    READY = "READY"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED_RESOURCE = "BLOCKED_RESOURCE"
    CONFIG_ERROR = "CONFIG_ERROR"


@dataclass
class DeviceProfile:
    """Static device type definition shared by one or more DUT instances."""

    name: str
    protocol: str
    platform: str
    capabilities: list[str] = field(default_factory=list)
    operation_mode: str = "physical"
    firmware: str = "unknown"
    ip: str | None = None


# Backward-compatible name for the original P0 model.
DeviceConfig = DeviceProfile


@dataclass
class DUTInstance:
    """A real lab DUT instance described by Lab/Instance Config."""

    id: str
    profile: str
    ip: str | None = None
    ssh_port: int | None = None
    resources: dict[str, str] = field(default_factory=dict)


@dataclass
class DUTPool:
    """The set of real DUT instances available to one runtime."""

    instances: list[DUTInstance] = field(default_factory=list)
    profile_capabilities: dict[str, set[str]] = field(default_factory=dict)

    def get(self, instance_id: str) -> DUTInstance:
        for instance in self.instances:
            if instance.id == instance_id:
                return instance
        raise KeyError(f"Unknown DUT instance '{instance_id}'")


@dataclass
class LabConfig:
    """Lab/SW config (slide4): environment and available resources.

    Only a secret reference is stored, never plaintext credentials.
    """

    name: str
    host: str
    secret_ref: str | None = None
    resources: dict[str, str] = field(default_factory=dict)


@dataclass
class RuntimeContext:
    """Runtime Context with the profile and real DUT Pool merged."""

    device: DeviceProfile
    lab: LabConfig
    resources: dict[str, str] = field(default_factory=dict)
    dut_pool: DUTPool = field(default_factory=DUTPool)


@dataclass
class CaseStep:
    """One abstract atomic step: an action plus its expected result."""

    action: str
    expected: str
    timeout: int = 30


@dataclass
class AtomicStep:
    """Compiled abstract action or verification, free of OEM commands."""

    kind: str
    name: str
    timeout: int = 30


@dataclass
class TestCase:
    """Test intent (WHAT) plus filter metadata; contains no OEM-specific HOW."""

    __test__ = False  # prevent pytest from collecting this domain model as a test class
    id: str
    name: str
    description: str
    required_capabilities: list[str] = field(default_factory=list)
    steps: list[CaseStep] = field(default_factory=list)
    # Empty list means "applicable to any value" for that filter dimension.
    protocols: list[str] = field(default_factory=list)
    operation_modes: list[str] = field(default_factory=list)
    required_resources: list[str] = field(default_factory=list)
    required_dut_roles: list[str] = field(default_factory=list)
    role_capabilities: dict[str, list[str]] = field(default_factory=dict)
    scope: str = "common"
    tags: list[str] = field(default_factory=list)


@dataclass
class PlanItem:
    """A case bound to the provider that will execute it."""

    case: TestCase
    provider: str
    selected_capabilities: list[str]
    role_bindings: dict[str, str] = field(default_factory=dict)
    resource_bindings: dict[str, str] = field(default_factory=dict)
    compiled_steps: list[AtomicStep] = field(default_factory=list)


@dataclass
class TestPlan:
    """Immutable execution contract (slide6) shared by CLI and GUI."""

    __test__ = False  # prevent pytest from collecting this domain model as a test class
    plan_id: str
    device: str
    protocol: str
    platform: str
    items: list[PlanItem] = field(default_factory=list)
    dut_pool: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    """Structured verdict + detail for a single case (slide7 step 9)."""

    case_id: str
    case_name: str
    status: str
    provider: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Aggregated evidence for a whole plan run."""

    plan_id: str
    evidences: list[Evidence] = field(default_factory=list)

