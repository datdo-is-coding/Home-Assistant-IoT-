"""Fail-closed preflight for the isolated commissioning Rules namespaces."""
from __future__ import annotations

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))


class CommissioningRulesTests(unittest.TestCase):
    def setUp(self):
        try:
            self.validate = importlib.import_module("commissioning_rules").validate_commissioning_rules
        except ModuleNotFoundError:
            self.fail("commissioning Rules preflight helper is missing")
        self.document = json.loads(
            (Path(__file__).resolve().parents[1] / "firebase" / "commissioning.rules.json").read_text()
        )

    def test_accepts_fragment_and_preserves_unrelated_devices_rules(self):
        self.document["rules"]["devices"] = {".read": True, ".write": "auth != null"}
        before = deepcopy(self.document)
        self.assertIsNone(self.validate(self.document))
        self.assertEqual(self.document, before)

    def test_accepts_absent_or_constant_false_root_grants(self):
        for value in (False, "false", None):
            with self.subTest(value=value):
                document = deepcopy(self.document)
                for name in (".read", ".write"):
                    if value is None:
                        document["rules"].pop(name, None)
                    else:
                        document["rules"][name] = value
                self.assertIsNone(self.validate(document))

    def test_rejects_root_grants_even_when_protected_children_deny(self):
        for name in (".read", ".write"):
            for value in (True, "true", "auth != null", "auth.uid == 'installer'", 0, None, {}):
                with self.subTest(name=name, value=value):
                    document = deepcopy(self.document)
                    document["rules"][name] = value
                    with self.assertRaises(ValueError):
                        self.validate(document)

    def test_rejects_root_wildcards_even_with_false_rules(self):
        for value in ({".read": True}, {".write": "auth != null"}, {".read": False}):
            with self.subTest(value=value):
                document = deepcopy(self.document)
                document["rules"]["$namespace"] = value
                with self.assertRaises(ValueError):
                    self.validate(document)

    def test_rejects_malformed_or_missing_protected_namespaces(self):
        for document in (None, [], {}, {"rules": []}, {"rules": {}}):
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    self.validate(document)
        for namespace in ("gateway_access", "gateways", "gateway_rpc"):
            with self.subTest(namespace=namespace):
                document = deepcopy(self.document)
                del document["rules"][namespace]
                with self.assertRaises(ValueError):
                    self.validate(document)

    def test_rejects_ancestor_grants_and_literal_children_inside_protected_namespaces(self):
        for namespace in ("gateway_access", "gateways", "gateway_rpc"):
            for extra in ({".read": True}, {".write": True}, {"known_gateway": {".write": True}}):
                with self.subTest(namespace=namespace, extra=extra):
                    document = deepcopy(self.document)
                    document["rules"][namespace].update(extra)
                    with self.assertRaises(ValueError):
                        self.validate(document)

    def test_rejects_deep_permissions_and_validation_changes(self):
        mutations = (
            (("gateway_access", "$uid", ".read"), "auth != null"),
            (("gateways", "$gateway_id", "status", ".read"), True),
            (("gateway_rpc", "$gateway_id", "requests", "$uid", "$request_id", ".write"), "auth != null"),
            (("gateway_rpc", "$gateway_id", "requests", "$uid", "$request_id", "$other", ".validate"), True),
            (("gateway_rpc", "$gateway_id", "responses", "$uid", ".read"), True),
        )
        for path, value in mutations:
            with self.subTest(path=path):
                document = deepcopy(self.document)
                target = document["rules"]
                for child in path[:-1]:
                    target = target[child]
                target[path[-1]] = value
                with self.assertRaises(ValueError):
                    self.validate(document)


if __name__ == "__main__":
    unittest.main()
