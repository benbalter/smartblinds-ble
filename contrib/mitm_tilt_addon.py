"""mitmproxy addon: capture + redact Tilt / MySmartBlinds cloud traffic.

Usage:
    mitmdump -s contrib/mitm_tilt_addon.py

For any flow touching the Tilt / MySmartBlinds API it:
  - prints a one-line summary plus any pairingKey / mac / key fields (secrets
    shown masked, e.g. 6BE8…2EE2), and
  - writes a REDACTED copy of the request+response to ./tilt-capture/ so you can
    share the schema safely.

Redaction masks the *values* of any field whose name contains key/token/secret/
password/authorization (and those request headers), preserving structure and
non-secret fields (names, ids, MACs, positions) for analysis.

Tested with mitmproxy 10/11 (stdlib logging, not the deprecated ctx.log).
"""

from __future__ import annotations

import json
import logging
import os
import re

from mitmproxy import http

HOSTS = ("tiltsmarthome.com", "mysmartblinds.com", "mysmartblinds.auth0.com")
SECRET_FIELD = re.compile(r"(key|token|secret|passwd|password|authorization)", re.I)
OUTDIR = "tilt-capture"

_counter = {"n": 0}


def _mask(val: object) -> str:
    s = str(val)
    if len(s) <= 10:
        return f"<redacted:{len(s)}>"
    return f"{s[:4]}…{s[-4:]} (len {len(s)})"


def _redact(obj: object) -> object:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, (str, int, float)) and SECRET_FIELD.search(k):
                out[k] = f"<redacted:{len(str(v))}>"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def _redact_headers(headers: http.Headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        if SECRET_FIELD.search(k):
            parts = v.split(" ", 1)
            if len(parts) == 2:  # keep scheme, mask token (e.g. "Bearer <redacted>")
                out[k] = f"{parts[0]} <redacted:{len(parts[1])}>"
            else:
                out[k] = f"<redacted:{len(v)}>"
        else:
            out[k] = v
    return out


def _print_hits(obj: object, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{path}.{k}" if path else k
            if isinstance(v, (str, int, float, bool)):
                if SECRET_FIELD.search(k):
                    logging.warning(f"[tilt]   {kp} = {_mask(v)}")
                elif re.search(r"(mac|name|id|position|model)", k, re.I):
                    logging.warning(f"[tilt]   {kp} = {v!r}")
            _print_hits(v, kp)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _print_hits(v, f"{path}[{i}]")


def _parse(body: str) -> object | None:
    try:
        return json.loads(body)
    except Exception:
        return None


def response(flow: http.HTTPFlow) -> None:
    host = flow.request.pretty_host
    if not any(h in host for h in HOSTS):
        return

    status = flow.response.status_code if flow.response else "?"
    logging.warning(f"[tilt] {flow.request.method} {status} {flow.request.pretty_url}")

    resp_body = (flow.response.get_text(strict=False) or "") if flow.response else ""
    resp_json = _parse(resp_body)
    if resp_json is not None:
        _print_hits(resp_json)

    try:
        os.makedirs(OUTDIR, exist_ok=True)
        _counter["n"] += 1
        req_body = flow.request.get_text(strict=False) or ""
        req_json = _parse(req_body)
        rec = {
            "request": {
                "method": flow.request.method,
                "url": flow.request.pretty_url,
                "headers": _redact_headers(flow.request.headers),
                "body": _redact(req_json) if req_json is not None else req_body[:500],
            },
            "response": {
                "status": status,
                "json": _redact(resp_json) if resp_json is not None else resp_body[:500],
            },
        }
        fn = os.path.join(OUTDIR, f"{_counter['n']:03d}-{flow.request.method}.json")
        with open(fn, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2)
        logging.warning(f"[tilt]   saved redacted -> {fn}")
    except Exception as exc:  # noqa: BLE001 - never let capture-write kill the proxy
        logging.warning(f"[tilt]   (capture write failed: {exc})")
