"""Reusable transport / control tools shared across OEM integrations.

These are vendor-neutral connection mechanisms an OEM provider can build on:
HTTP (``http_client``) today, with room for SSH, Telnet or serial control for
devices driven by shell commands instead of HTTP. Distinct from ``core`` (the
framework abstractions) and ``oem`` (device-specific HOW).
"""
