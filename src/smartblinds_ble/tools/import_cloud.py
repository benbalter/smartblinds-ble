"""CLI: pull MAC + BLE key for every shade from the cloud and save them.

    $ smartblinds-import-cloud                 # prompts for email + password
    $ smartblinds-import-cloud -u you@example.com -o my-shades.json

Credentials may also come from the SMARTBLINDS_USERNAME / SMARTBLINDS_PASSWORD
environment variables. The password is never printed or written to the output.

⚠️  The output file contains BLE keys (secrets) — keep it safe and out of version
    control. Do this NOW while the vendor cloud is still online; see cloud.py.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from ..cloud import fetch_blinds


def main() -> None:
    parser = argparse.ArgumentParser(description="Import shade MAC+key from the cloud account.")
    parser.add_argument("-u", "--username", default=os.environ.get("SMARTBLINDS_USERNAME"))
    parser.add_argument("-o", "--output", default="smartblinds-keys.json")
    args = parser.parse_args()

    username = args.username or input("Cloud account email: ").strip()
    password = os.environ.get("SMARTBLINDS_PASSWORD") or getpass.getpass("Password: ")

    try:
        blinds = fetch_blinds(username, password)
    except ImportError as exc:
        sys.exit(str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any auth/network failure to the user
        sys.exit(f"Cloud import failed: {exc}")

    if not blinds:
        sys.exit("Login succeeded but no shades were found on the account.")

    payload = [b.as_dict() for b in blinds]
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    print(f"Saved {len(blinds)} shade(s) to {args.output}:", file=sys.stderr)
    for b in blinds:
        room = f" [{b.room}]" if b.room else ""
        print(f"  {b.name}{room}: {b.mac}  key={b.key}", file=sys.stderr)
    print(
        "\nKeep this file safe — it contains BLE keys and is your offline backup "
        "if the cloud shuts down.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
