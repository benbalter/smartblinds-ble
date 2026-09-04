"""CLI: pull MAC + BLE key for every shade from the cloud and save them.

    $ smartblinds-import-cloud                 # prompts for email + password
    $ smartblinds-import-cloud -u you@example.com -o my-shades.json
    $ smartblinds-import-cloud --include-deleted --token access_token
    $ smartblinds-import-cloud --debug         # probe both tokens, print counts

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

from ..cloud import diagnose, fetch_blinds


def _credentials(args: argparse.Namespace) -> tuple[str, str]:
    username = args.username or os.environ.get("SMARTBLINDS_USERNAME") or input("Cloud account email: ").strip()
    password = os.environ.get("SMARTBLINDS_PASSWORD") or getpass.getpass("Password: ")
    return username, password


def main() -> None:
    parser = argparse.ArgumentParser(description="Import shade MAC+key from the cloud account.")
    parser.add_argument("-u", "--username", default=None)
    parser.add_argument("-o", "--output", default="smartblinds-keys.json")
    parser.add_argument("--include-deleted", action="store_true",
                        help="also export shades the account has soft-deleted")
    parser.add_argument("--token", choices=["id_token", "access_token"], default="id_token",
                        help="which auth token to send (default: id_token)")
    parser.add_argument("--debug", action="store_true",
                        help="probe both tokens and print counts instead of exporting")
    args = parser.parse_args()

    username, password = _credentials(args)

    if args.debug:
        try:
            print(diagnose(username, password))
        except ImportError as exc:
            sys.exit(str(exc))
        except Exception as exc:  # noqa: BLE001 - surface any auth/network failure
            sys.exit(f"Diagnose failed: {exc}")
        return

    try:
        blinds = fetch_blinds(
            username, password, include_deleted=args.include_deleted, token=args.token
        )
    except ImportError as exc:
        sys.exit(str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any auth/network failure
        sys.exit(f"Cloud import failed: {exc}")

    if not blinds:
        sys.exit(
            "Login succeeded but no shades were found. Try `--debug` to see what the "
            "account returns, `--include-deleted`, or `--token access_token`."
        )

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump([b.as_dict() for b in blinds], fh, indent=2)

    print(f"Saved {len(blinds)} shade(s) to {args.output}:", file=sys.stderr)
    for b in blinds:
        room = f" [{b.room}]" if b.room else ""
        flag = " (deleted)" if b.deleted else ""
        print(f"  {b.name}{room}{flag}: {b.mac}  key={b.key}", file=sys.stderr)
    print(
        "\nKeep this file safe — it contains BLE keys and is your offline backup "
        "if the cloud shuts down.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
