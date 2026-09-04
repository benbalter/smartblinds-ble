"""mitmproxy addon that surfaces Tilt / MySmartBlinds cloud secrets.

Usage:
    mitmweb  -s contrib/mitm_tilt_addon.py     # web UI at http://127.0.0.1:8081
    # or
    mitmproxy -s contrib/mitm_tilt_addon.py

Point your iPhone's Wi-Fi HTTP proxy at this machine (port 8080), install +
fully-trust the mitmproxy CA, then drive the Tilt app. Any response whose URL or
body mentions a blind/shade/key/mac is logged, with the interesting JSON fields
(anything with "passkey", "mac", or "key" in the field name) pulled out.

Tested with mitmproxy 10/11 (uses stdlib logging, not the deprecated ctx.log).
"""

from __future__ import annotations

import json
import logging

from mitmproxy import http

# A flow is "interesting" if its URL or body mentions any of these.
INTEREST = ("passkey", "mac", "blind", "shade", "tilt")

# Field names worth extracting from a JSON response body.
SECRET_FIELDS = ("passkey", "mac", "key")


def _walk(obj: object, hits: list[tuple[str, object]], path: str = "") -> None:
    """Recursively collect (json_path, value) for secret-looking scalar fields."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{path}.{k}" if path else k
            if isinstance(v, (str, int, float, bool)) and any(
                s in k.lower() for s in SECRET_FIELDS
            ):
                hits.append((kp, v))
            _walk(v, hits, kp)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk(v, hits, f"{path}[{i}]")


def response(flow: http.HTTPFlow) -> None:
    url = flow.request.pretty_url
    body = flow.response.get_text(strict=False) or "" if flow.response else ""
    if not any(s in (url + body).lower() for s in INTEREST):
        return

    status = flow.response.status_code if flow.response else "?"
    logging.warning(f"[tilt] {flow.request.method} {status} {url}")

    # If the request was GraphQL, echo the operation so we know what was asked.
    req_body = flow.request.get_text(strict=False) or ""
    if "graphql" in url.lower() or '"query"' in req_body:
        try:
            q = json.loads(req_body).get("query", "")
            logging.warning(f"[tilt]   query: {' '.join(q.split())[:200]}")
        except Exception:
            pass

    try:
        data = json.loads(body)
    except Exception:
        logging.warning(f"[tilt]   (non-JSON body, {len(body)} bytes)")
        return

    hits: list[tuple[str, object]] = []
    _walk(data, hits)
    for jpath, val in hits:
        logging.warning(f"[tilt]   {jpath} = {val!r}")
    if not hits:
        logging.warning("[tilt]   (matched on URL/body but no secret-looking fields)")
