"""CLI: export every Tilt roller shade's MAC + BLE pairing key from the cloud.

    $ smartblinds-import-tilt                      # prompts for email + password
    $ smartblinds-import-tilt -u you@example.com -o my-shades.json
    $ smartblinds-import-tilt --include-bridges
    $ smartblinds-import-tilt --access-token "$TOKEN"   # skip the password grant
    $ smartblinds-import-tilt --debug              # print what the account exposes

This is the **Tilt** app's backend. If your shades were set up in the older
MySmartBlinds app, use `smartblinds-import-cloud` instead.

Credentials may also come from TILT_USERNAME / TILT_PASSWORD (or an already
captured token in TILT_ACCESS_TOKEN). The password is never printed or written
to the output.

⚠️  The output file contains BLE pairing keys (secrets) — keep it safe and out of
    version control. Do this NOW: these keys cannot be brute-forced or sniffed,
    so once the vendor cloud shuts down they are unrecoverable.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from ..tilt_cloud import TiltCloudError, diagnose, fetch_devices


def _credentials(args: argparse.Namespace) -> tuple[str, str]:
    username = (
        args.username
        or os.environ.get("TILT_USERNAME")
        or input("Tilt account email: ").strip()
    )
    password = os.environ.get("TILT_PASSWORD") or getpass.getpass("Password: ")
    return username, password


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Tilt roller shade MAC + pairing key from the Tilt cloud."
    )
    parser.add_argument("-u", "--username", default=None)
    parser.add_argument("-o", "--output", default="tilt-keys.json")
    parser.add_argument(
        "--include-bridges",
        action="store_true",
        help="also export bridges (cloud-only MQTT clients; no local control path)",
    )
    parser.add_argument(
        "--access-token",
        default=None,
        help="use an already captured access_token instead of logging in "
        "(needed for MFA accounts); also read from TILT_ACCESS_TOKEN",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print what the account exposes instead of exporting",
    )
    args = parser.parse_args()

    token = args.access_token or os.environ.get("TILT_ACCESS_TOKEN")
    username = password = None
    if not token:
        username, password = _credentials(args)

    if args.debug:
        try:
            print(diagnose(username, password, access_token=token))
        except TiltCloudError as exc:
            sys.exit(str(exc))
        return

    try:
        devices = fetch_devices(
            username, password, access_token=token, include_bridges=args.include_bridges
        )
    except TiltCloudError as exc:
        sys.exit(str(exc))

    if not devices:
        sys.exit(
            "Login succeeded but the Tilt store listed no keyed devices. If your "
            "shades were set up in the older MySmartBlinds app they live in a "
            "different backend — use `smartblinds-import-cloud` instead. "
            "(`--debug` shows what the account exposes.)"
        )

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump([d.as_dict() for d in devices], fh, indent=2)

    print(f"Saved {len(devices)} device(s) to {args.output}:", file=sys.stderr)
    for device in devices:
        room = f" [{device.room}]" if device.room else ""
        kind = "" if device.kind == "roller_shade" else f" ({device.kind})"
        print(f"  {device.name}{room}{kind}: {device.mac}  key={device.key}", file=sys.stderr)
    print(
        "\nKeep this file safe — it holds pairing keys that cannot be brute-forced "
        "or sniffed. Back it up somewhere durable: when the vendor cloud shuts "
        "down, an un-exported key is gone for good.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
