"""Template OEM integration package.

Copy this folder and rename it to a vendor-specific package such as
``oem/ale700a`` or ``oem/xxxvendor``.
"""

from oem.template.action_url import ActionEvent, ActionUrlListener
from oem.template.provider import ExampleProvider

__all__ = [
    "ActionEvent",
    "ActionUrlListener",
    "ExampleProvider",
]
