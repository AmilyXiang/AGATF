"""ALE-700A OEM debug CLI: ``python -m oem.ale700a <command>``.

These are vendor-specific live-debug helpers that must NOT live in the neutral
``cli.py`` (which keeps only validate/list/plan/run):

- ``press``  send one Active URI key to a real phone (OEM action).
- ``listen`` start the callback listener and print phone events (generic
  mechanism from ``tools.callback_listener`` with the ALE-700A URL hint).
"""
from __future__ import annotations

import argparse
import json
import logging
import threading

from oem.ale700a.action_url import ActionUrlListener
from oem.ale700a.provider import ActiveUriClient

logger = logging.getLogger(__name__)


def press(args: argparse.Namespace) -> int:
    # Send a single Active URI key to a real phone for the simplest live check.
    # The password is read from an environment variable, never from the CLI.
    base_url = f"{args.protocol}://{args.ip}" + (f":{args.port}" if args.port else "")
    client = ActiveUriClient(
        base_url,
        username=args.user,
        secret_ref=args.secret_env,
        verify_tls=not args.insecure,
    )
    ok, detail = client.send(args.key)
    print(json.dumps(detail, indent=2))
    if not ok:
        logger.warning("press: phone did not accept key '%s'", args.key)
        return 1
    return 0


def listen(args: argparse.Namespace) -> int:
    # Start the callback listener and print phone status callbacks as they
    # arrive; used for manual verification against a real ALE-700A.
    listener = ActionUrlListener(
        host=args.host,
        port=args.port,
        on_event=lambda e: print(f"[event] {e.event} {e.params}"),
    ).start()
    print(f"Action URL listener on {listener.url}")
    print("Configure the phone Action URL to point here, e.g.:")
    print(f"  {listener.url}/action?event=call_established&mac=$mac&cid=$call_id&dt=$date_time")
    print("Press Ctrl+C to stop.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nStopping listener.")
    finally:
        listener.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m oem.ale700a", description="ALE-700A live-debug helpers")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default INFO)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    press_parser = subparsers.add_parser("press", help="Send one Active URI key to a real phone (simplest live check)")
    press_parser.add_argument("--ip", required=True, help="Phone IP address, e.g. 10.10.6.141")
    press_parser.add_argument("--key", required=True, help="Active URI key, e.g. SPEAKER or 'SPEAKER;1007;ENTER'")
    press_parser.add_argument("--protocol", default="http", choices=["http", "https"], help="Web protocol (default http)")
    press_parser.add_argument("--port", type=int, default=None, help="Web port (default: protocol default)")
    press_parser.add_argument("--user", default="admin", help="HTTP Basic user (default admin)")
    press_parser.add_argument("--secret-env", default="ALE700A_PASSWORD", help="Env var holding the phone password (default ALE700A_PASSWORD)")
    press_parser.add_argument("--insecure", action="store_true", help="Skip TLS cert verification (phones use self-signed certs)")
    press_parser.set_defaults(func=press)

    listen_parser = subparsers.add_parser("listen", help="Start the Action URL listener for phone status callbacks")
    listen_parser.add_argument("--host", default="0.0.0.0", help="Bind address (default 0.0.0.0)")
    listen_parser.add_argument("--port", type=int, default=8080, help="Bind port (default 8080)")
    listen_parser.set_defaults(func=listen)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
