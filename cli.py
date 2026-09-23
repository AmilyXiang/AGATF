"""CLI-first entrypoint (slide8): plan and run subcommands.

The CLI is the formal interface for Jenkins/CI/Batch. It builds a Runtime
Context, filters applicable cases, resolves providers into a Test Plan, and
executes that plan into evidence.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import oem  # noqa: F401 - imports register every OEM into the provider registry
from core import provider_registry
from core.executor import Executor
from core.exit_codes import ExitCode
from core.models import AtomicStep, CaseStep, DUTInstance, DUTPool, DeviceConfig, LabConfig, RuntimeContext, SelectionStatus, TestCase, TestPlan
from core.resolver import DutBindingError, ProviderBindingError, Resolver
from core.selection import filter_applicable_cases

logger = logging.getLogger(__name__)

# The Case Repository is always this single directory (slide6); selection is by
# --scope, so there is no --cases option.
CASES_DIR = "cases"


def load_json(path: str | Path) -> object:
    logger.debug("loading json %s", path)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_case_repository() -> list:
    # Load every case JSON from the single Case Repository (slide6).
    data: list = []
    for case_file in sorted(Path(CASES_DIR).glob("*.json")):
        data.extend(load_json(case_file))
    return data


def build_runtime_context(device_data: dict, lab_data: dict) -> RuntimeContext:
    # Merge HW config and Lab config into the single selection input (slide4).
    device = DeviceConfig(
        name=device_data["name"],
        protocol=device_data["protocol"],
        platform=device_data["platform"],
        capabilities=device_data.get("capabilities", []),
        operation_mode=device_data.get("operation_mode", "physical"),
        firmware=device_data.get("firmware", "unknown"),
    )
    lab = LabConfig(
        name=lab_data["name"],
        host=lab_data["host"],
        secret_ref=lab_data.get("secret_ref"),
        password=lab_data.get("password"),
        resources=lab_data.get("resources", {}),
        action_url_host=lab_data.get("action_url", {}).get("host", "0.0.0.0"),
        action_url_port=lab_data.get("action_url", {}).get("port", 8080),
    )
    raw_instances = lab_data.get("duts", lab_data.get("instances", []))
    instances = [
        DUTInstance(
            id=item["id"],
            profile=item.get("profile", device.name),
            ip=item.get("ip"),
            ssh_port=item.get("ssh_port"),
            number=item.get("number"),
            resources=item.get("resources", {}),
            control=item.get("control", {}),
        )
        for item in raw_instances
    ]
    if not instances:
        instances = [DUTInstance(id=device.name, profile=device.name)]

    logger.info("runtime context: device=%s protocol=%s mode=%s duts=%d", device.name, device.protocol, device.operation_mode, len(instances))
    return RuntimeContext(
        device=device,
        lab=lab,
        resources=lab_data.get("resources", {}),
        dut_pool=DUTPool(instances, {device.name: set(device.capabilities)}),
    )


def parse_cases(case_data: list[dict]) -> list[TestCase]:
    # Turn raw case JSON into strongly typed TestCase/CaseStep objects.
    logger.debug("parse_cases: %d raw cases", len(case_data))
    cases: list[TestCase] = []
    for item in case_data:
        steps = [
            CaseStep(
                action=step["action"],
                expected=step["expected"],
                timeout=step.get("timeout", 30),
            )
            for step in item.get("steps", [])
        ]
        cases.append(
            TestCase(
                id=item["id"],
                name=item["name"],
                description=item.get("description", ""),
                required_capabilities=item.get("required_capabilities", []),
                steps=steps,
                protocols=item.get("protocols", []),
                operation_modes=item.get("operation_modes", []),
                required_resources=item.get("required_resources", []),
                required_dut_roles=item.get("required_dut_roles", []),
                role_capabilities=item.get("role_capabilities", {}),
                scope=item.get("scope", "common"),
                tags=item.get("tags", []),
            )
        )
    return cases


def generate_plan(args: argparse.Namespace) -> None:
    # slide7 steps 1-6: load config, build context, filter cases, bind, plan.
    logger.info("plan: device=%s lab=%s scope=%s", args.device, args.lab, getattr(args, "scope", None))
    device_data = load_json(args.device)
    lab_data = load_json(args.lab)
    case_data = load_case_repository()
    context = build_runtime_context(device_data, lab_data)

    # Registry: the Resolver picks a provider by backend (slide11); OEMs are
    # sourced from the registry so the CLI imports no vendor class.
    resolver = Resolver(provider_registry.default_providers())
    all_cases = parse_cases(case_data)

    # Configuration-driven selection: only applicable cases enter the plan.
    scope = getattr(args, "scope", None)
    case_objs, outcomes = filter_applicable_cases(all_cases, context, scope)
    for outcome in outcomes:
        if outcome.status != SelectionStatus.READY:
            print(f"{outcome.status.value} {outcome.case.id}: {outcome.reason}")

    resource_bindings = {
        outcome.case.id: outcome.resource_bindings or {}
        for outcome in outcomes
        if outcome.status == SelectionStatus.READY
    }

    # Fail fast on binding problems, but surface them as structured exit codes
    # (slide6) instead of a traceback: DUT shortage -> BLOCKED_RESOURCE, missing
    # provider -> CONFIG_ERROR.
    try:
        plan = resolver.build_plan(
            context.device.name,
            context.device.protocol,
            context.device.platform,
            set(context.device.capabilities),
            case_objs,
            context.dut_pool,
            resource_bindings,
            context.device.operation_mode,
        )
    except DutBindingError as exc:
        print(f"BLOCKED_RESOURCE {exc}")
        logger.warning("plan: DUT binding failed: %s", exc)
        return ExitCode.BLOCKED_RESOURCE
    except ProviderBindingError as exc:
        print(f"CONFIG_ERROR {exc}")
        logger.warning("plan: provider binding failed: %s", exc)
        return ExitCode.CONFIG_ERROR

    # Freeze audit / reproducibility metadata with the plan (slide7): a unique
    # run_id, the lab environment, the selected scope, firmware under test, the
    # generation timestamp and the artifacts this run is expected to produce.
    generated_at = datetime.now(timezone.utc)
    plan.plan_id = f"{context.device.name}-{context.device.protocol}-{context.device.platform}-{generated_at:%Y%m%d%H%M%S}"
    plan.environment = context.lab.name
    plan.scope = scope or "all"
    plan.firmware = context.device.firmware
    plan.generated_at = generated_at.isoformat()
    plan.expected_artifacts = ["junit"]

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("plan: %d items bound, writing %s", len(plan.items), out_path)
    payload = {
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "generated_at": plan.generated_at,
        "environment": plan.environment,
        "scope": plan.scope,
        "device": plan.device,
        "protocol": plan.protocol,
        "platform": plan.platform,
        "firmware": plan.firmware,
        "expected_artifacts": plan.expected_artifacts,
        "dut_pool": plan.dut_pool,
        "items": [
            {
                "case": {
                    "id": item.case.id,
                    "name": item.case.name,
                    "description": item.case.description,
                    "required_capabilities": item.case.required_capabilities,
                    "required_dut_roles": item.case.required_dut_roles,
                    "role_capabilities": item.case.role_capabilities,
                    "steps": [
                        {
                            "action": step.action,
                            "expected": step.expected,
                            "timeout": step.timeout,
                        }
                        for step in item.case.steps
                    ],
                },
                "provider": item.provider,
                "selected_capabilities": item.selected_capabilities,
                "role_bindings": item.role_bindings,
                "resource_bindings": item.resource_bindings,
                "compiled_steps": [
                    {
                        "kind": step.kind,
                        "name": step.name,
                        "timeout": step.timeout,
                    }
                    for step in item.compiled_steps
                ],
            }
            for item in plan.items
        ],
    }
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print(f"Generated plan: {out_path}")
    logger.info("plan: done -> %s", out_path)
    return ExitCode.SUCCESS


def validate_config(args: argparse.Namespace) -> int:
    # Step 1 only: validate config and derive case status; never execute.
    logger.info("validate: device=%s lab=%s scope=%s", args.device, args.lab, getattr(args, "scope", None))
    device_data = load_json(args.device)
    lab_data = load_json(args.lab)
    case_data = load_case_repository()
    context = build_runtime_context(device_data, lab_data)

    all_cases = parse_cases(case_data)
    scope = getattr(args, "scope", None)
    _, outcomes = filter_applicable_cases(all_cases, context, scope)

    has_config_error = False
    has_blocked = False
    for outcome in outcomes:
        print(f"{outcome.status.value} {outcome.case.id}: {outcome.reason}")
        if outcome.status == SelectionStatus.CONFIG_ERROR:
            has_config_error = True
        elif outcome.status == SelectionStatus.BLOCKED_RESOURCE:
            has_blocked = True

    if has_config_error:
        logger.warning("validate: CONFIG_ERROR detected")
        return ExitCode.CONFIG_ERROR
    if has_blocked:
        logger.warning("validate: BLOCKED_RESOURCE detected")
        return ExitCode.BLOCKED_RESOURCE
    logger.info("validate: OK")
    return ExitCode.SUCCESS


def list_cases(args: argparse.Namespace) -> int:
    # List every case with its selection status; preparation only, no execution.
    logger.info("list: device=%s lab=%s scope=%s", args.device, args.lab, getattr(args, "scope", None))
    device_data = load_json(args.device)
    lab_data = load_json(args.lab)
    case_data = load_case_repository()
    context = build_runtime_context(device_data, lab_data)

    all_cases = parse_cases(case_data)
    scope = getattr(args, "scope", None)
    _, outcomes = filter_applicable_cases(all_cases, context, scope)

    for outcome in outcomes:
        print(f"{outcome.status.value:<16} {outcome.case.id:<16} {outcome.case.name}")
    logger.info("list: %d cases listed", len(outcomes))
    return ExitCode.SUCCESS


def _write_junit(result, path: Path) -> None:
    # Minimal JUnit XML so Jenkins can publish the run as test results.
    failures = sum(1 for e in result.evidences if e.status != "pass")
    testsuite = ET.Element(
        "testsuite",
        name=result.plan_id,
        tests=str(len(result.evidences)),
        failures=str(failures),
    )
    for evidence in result.evidences:
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            classname=result.plan_id,
            name=evidence.case_id,
        )
        if evidence.status != "pass":
            failure = ET.SubElement(testcase, "failure", message=evidence.status)
            failure.text = evidence.details.get("summary", "")

    path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(testsuite)
    ET.indent(tree, space="  ")  # pretty-print with 2-space indentation
    tree.write(path, encoding="utf-8", xml_declaration=True)
    logger.info("junit: wrote %d tests (%d failures) to %s", len(result.evidences), failures, path)


def _build_plan_from_json(plan_data: dict) -> TestPlan:
    plan_items = []
    for item in plan_data["items"]:
        case_payload = item["case"]
        case = TestCase(
            id=case_payload["id"],
            name=case_payload["name"],
            description=case_payload.get("description", ""),
            required_capabilities=case_payload.get("required_capabilities", []),
            required_dut_roles=case_payload.get("required_dut_roles", []),
            role_capabilities=case_payload.get("role_capabilities", {}),
            steps=[
                CaseStep(
                    action=step["action"],
                    expected=step["expected"],
                    timeout=step.get("timeout", 30),
                )
                for step in case_payload.get("steps", [])
            ],
        )
        plan_items.append(
            type(
                "PlanItemStub",
                (),
                {
                    "case": case,
                    "provider": item["provider"],
                    "selected_capabilities": item.get("selected_capabilities", []),
                    "role_bindings": item.get("role_bindings", {}),
                    "resource_bindings": item.get("resource_bindings", {}),
                    "compiled_steps": [
                        AtomicStep(
                            kind=step["kind"],
                            name=step["name"],
                            timeout=step.get("timeout", 30),
                        )
                        for step in item.get("compiled_steps", [])
                    ],
                },
            )()
        )

    plan = TestPlan(
        plan_id=plan_data["plan_id"],
        device=plan_data.get("device", "unknown"),
        protocol=plan_data.get("protocol", "unknown"),
        platform=plan_data.get("platform", "unknown"),
        items=plan_items,
        dut_pool=plan_data.get("dut_pool", []),
    )
    return plan


def run_plan(args: argparse.Namespace) -> int:
    # slide7 steps 8-9: rebuild the plan from JSON, execute it, print evidence.
    logger.info("run: plan=%s junit=%s live=%s", args.plan, getattr(args, "junit", None), getattr(args, "live", False))
    plan_data = load_json(args.plan)

    # Providers come from the registry so the executor resolves each item by
    # name without the CLI importing any vendor class (slide11/12). In --live
    # mode the OEM's registered live builder replaces its dry-run provider.
    providers = {p.name: p for p in provider_registry.default_providers()}
    dut_numbers: dict[str, str] = {}
    teardown = None
    if getattr(args, "live", False):
        if not args.device or not args.lab:
            logger.error("run --live requires --device and --lab")
            return ExitCode.CONFIG_ERROR
        device_data = load_json(args.device)
        lab_data = load_json(args.lab)
        operation_mode = device_data.get("operation_mode", "")
        live = provider_registry.build_live_provider(
            operation_mode,
            device_data,
            lab_data,
            {
                "insecure": getattr(args, "insecure", False),
                "number": getattr(args, "number", None),
                "dut": getattr(args, "dut", None),
            },
        )
        providers[live.provider.name] = live.provider
        dut_numbers = live.dut_numbers
        teardown = live.teardown

    executor = Executor(providers, dut_numbers=dut_numbers)
    plan = _build_plan_from_json(plan_data)

    try:
        result = executor.run_plan(plan)
    finally:
        if teardown is not None:
            teardown()
    print(json.dumps({
        "plan_id": result.plan_id,
        "evidences": [
            {
                "case_id": e.case_id,
                "case_name": e.case_name,
                "status": e.status,
                "provider": e.provider,
                "details": e.details,
            }
            for e in result.evidences
        ],
    }, indent=2))

    junit_path = getattr(args, "junit", None)
    if junit_path:
        _write_junit(result, Path(junit_path))
        print(f"Wrote JUnit: {junit_path}")

    # Step 9: a failed case yields a stable non-zero exit code for Jenkins.
    failed = sum(1 for e in result.evidences if e.status != "pass")
    if failed:
        logger.warning("run: %d/%d cases failed", failed, len(result.evidences))
        return ExitCode.TEST_FAILURE
    logger.info("run: all %d cases passed", len(result.evidences))
    return ExitCode.SUCCESS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeskPhone automation CLI-first core")
    parser.add_argument(
        "--log-level",
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity for debugging (default DEBUG)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate config and case status without executing")
    validate_parser.add_argument("--device", required=True, help="Device config JSON (protocol / capabilities / operation_mode)")
    validate_parser.add_argument("--lab", required=True, help="Lab config JSON (DUT pool / resources / bindings)")
    validate_parser.add_argument("--scope", default=None, help="Only evaluate cases matching this scope (common / sip / noe)")
    validate_parser.set_defaults(func=validate_config)

    list_parser = subparsers.add_parser("list", help="List cases with their selection status")
    list_parser.add_argument("--device", required=True, help="Device config JSON (protocol / capabilities / operation_mode)")
    list_parser.add_argument("--lab", required=True, help="Lab config JSON (DUT pool / resources / bindings)")
    list_parser.add_argument("--scope", default=None, help="Only list cases matching this scope (common / sip / noe)")
    list_parser.set_defaults(func=list_cases)

    plan_parser = subparsers.add_parser("plan", help="Generate a plan from config and case data")
    plan_parser.add_argument("--device", required=True, help="Device config JSON (protocol / capabilities / operation_mode)")
    plan_parser.add_argument("--lab", required=True, help="Lab config JSON (DUT pool / resources / bindings)")
    plan_parser.add_argument("--output", required=True, help="Output path for the generated plan JSON")
    plan_parser.add_argument("--scope", default=None, help="Only include cases matching this scope (common / sip / noe)")
    plan_parser.set_defaults(func=generate_plan)

    run_parser = subparsers.add_parser("run", help="Execute a generated plan")
    run_parser.add_argument("--plan", required=True, help="Generated plan JSON to execute")
    run_parser.add_argument("--junit", default=None, help="Write JUnit XML results to this path")
    run_parser.add_argument("--live", action="store_true", help="Drive a real device via its registered live provider instead of the stub")
    run_parser.add_argument("--device", default=None, help="Device config (required with --live)")
    run_parser.add_argument("--lab", default=None, help="Lab config with credentials/action_url (required with --live)")
    run_parser.add_argument("--number", default=None, help="Dial/transfer target number for live actions")
    run_parser.add_argument("--dut", default=None, help="DUT id to control in --live mode (default: first DUT in lab)")
    run_parser.add_argument("--insecure", action="store_true", help="Skip TLS verification for self-signed phone certs")
    run_parser.set_defaults(func=run_plan)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    # Logs go to stderr so stdout stays machine-parseable for Jenkins/CI.
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d: %(message)s",
        stream=sys.stderr,
    )
    logger.info("command: %s", args.command)
    # Every command returns a structured ExitCode consumed by Jenkins/CI.
    exit_code = args.func(args)
    logger.info("command %s exit code: %s", args.command, int(exit_code) if exit_code is not None else 0)
    sys.exit(int(exit_code) if exit_code is not None else int(ExitCode.SUCCESS))


if __name__ == "__main__":
    main()
