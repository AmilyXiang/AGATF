"""Structured CLI exit codes (P0-C).

Stable process exit codes so Jenkins/CI can branch on the outcome without
parsing stdout. argparse already uses 1 for usage errors.
"""
from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0            # all good / all cases passed
    USAGE_ERROR = 1        # reserved for argparse usage errors
    CONFIG_ERROR = 2       # invalid config or a CONFIG_ERROR case
    BLOCKED_RESOURCE = 3   # DUT or bench resources insufficient
    TEST_FAILURE = 4       # plan executed but at least one case failed
