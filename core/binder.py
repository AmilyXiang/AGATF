"""Resource binding for the preparation stage of the v2 runtime.

Maps each logical resource a Case declares (e.g. "audio") to a real lab
resource handle (e.g. "mic-02") from the Runtime Context. Physical resources
(Robot / Camera / Audio / Power) are only meaningful for physical operation
mode, but this binder does NOT branch on operation_mode: it binds every
declared required_resource unconditionally. Whether a resource is needed is
decided by Case metadata, not by this function.
"""
from __future__ import annotations

import logging

from core.models import RuntimeContext, TestCase

logger = logging.getLogger(__name__)


def bind_resources(case: TestCase, context: RuntimeContext) -> tuple[dict[str, str], list[str]]:
    """Map each logical Case resource name to a real lab resource handle."""
    bindings: dict[str, str] = {}
    missing: list[str] = []
    for resource_name in case.required_resources:
        handle = context.resources.get(resource_name)
        if handle is None:
            missing.append(resource_name)
        else:
            bindings[resource_name] = handle
    logger.debug("bind_resources %s: bound=%s missing=%s", case.id, bindings, missing)
    return bindings, missing
