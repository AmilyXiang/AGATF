import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from cli import generate_plan, list_cases, run_plan, validate_config
from core.exit_codes import ExitCode


class _CfgArgs:
    device = "tests/fixtures/device.json"
    lab = "tests/fixtures/lab.json"
    cases = "cases"
    scope = "common"


def test_validate_returns_success_for_valid_common_scope(capsys):
    code = validate_config(_CfgArgs())
    out = capsys.readouterr().out
    assert code == ExitCode.SUCCESS
    assert "NOT_APPLICABLE TC_SIP_REG_001" in out


def test_validate_reports_blocked_resource(tmp_path):
    lab = json.loads(Path("tests/fixtures/lab.json").read_text(encoding="utf-8"))
    lab["resources"].pop("audio", None)
    lab_path = tmp_path / "lab.json"
    lab_path.write_text(json.dumps(lab), encoding="utf-8")

    class Args(_CfgArgs):
        lab = str(lab_path)

    assert validate_config(Args()) == ExitCode.BLOCKED_RESOURCE


def test_list_outputs_status_and_returns_success(capsys):
    code = list_cases(_CfgArgs())
    out = capsys.readouterr().out
    assert code == ExitCode.SUCCESS
    assert "READY" in out
    assert "TC_CALL_001" in out


def test_run_returns_success_and_writes_junit(tmp_path):
    plan_path = tmp_path / "plan.json"
    junit_path = tmp_path / "results.xml"

    class PlanArgs:
        device = "tests/fixtures/device.json"
        lab = "tests/fixtures/lab.json"
        cases = "cases"
        output = str(plan_path)
        scope = "common"

    assert generate_plan(PlanArgs()) == ExitCode.SUCCESS

    class RunArgs:
        plan = str(plan_path)
        junit = str(junit_path)

    assert run_plan(RunArgs()) == ExitCode.SUCCESS

    tree = ET.parse(junit_path)
    root = tree.getroot()
    assert root.tag == "testsuite"
    assert root.attrib["failures"] == "0"
    assert int(root.attrib["tests"]) >= 1
