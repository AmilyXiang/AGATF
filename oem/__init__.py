"""OEM-specific device integrations (vendor HOW).

Each subpackage implements the Provider-layer HOW for one OEM device family,
keeping vendor specifics out of the vendor-neutral ``core`` package.

Importing this package registers every known OEM into the provider registry so
the CLI/Executor can resolve them by backend without importing any vendor
(slide13 / slide16 decision 4). Adding a new OEM = add its import here.
"""
from oem import ale700a  # noqa: F401 - imported for registration side effect
