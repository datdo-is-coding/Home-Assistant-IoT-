"""Verify deployed commissioning Rules without touching unrelated namespaces."""
from __future__ import annotations

import hashlib
import json


_PROTECTED_NAMESPACES = ("gateway_access", "gateways", "gateway_rpc")
# Pin the reviewed fragment independently of any runtime file or Firebase SDK.
_EXPECTED_SHA256 = "2fa91ada6d4f8eea33f6082530ab50c662df2e6370f66b36b45fd5f3f4514c96"


def validate_commissioning_rules(document: object) -> None:
    """Raise ValueError unless the full Rules document isolates commissioning.

    Accept only the exact protected subtrees in firebase/commissioning.rules.json.
    Root grants cascade past child denials, so only absent/constant-false root
    grants and no root wildcard are accepted. Other literal namespaces, including
    existing devices Rules, are inspected by their owner and are never changed.
    """
    if not isinstance(document, dict) or not isinstance(document.get("rules"), dict):
        raise ValueError("commissioning requires a full Firebase Rules document")
    rules = document["rules"]
    for permission in (".read", ".write"):
        if permission in rules and rules[permission] is not False and rules[permission] != "false":
            raise ValueError(f"unsafe root {permission}: only absent or false is allowed")
    if any(not isinstance(key, str) or key.startswith("$") for key in rules):
        raise ValueError("root wildcard Rules could bypass commissioning isolation")
    protected = {key: rules.get(key) for key in _PROTECTED_NAMESPACES}
    try:
        canonical = json.dumps(protected, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid commissioning Rules document") from exc
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != _EXPECTED_SHA256:
        raise ValueError("commissioning Rules differ from the reviewed namespace fragment")
