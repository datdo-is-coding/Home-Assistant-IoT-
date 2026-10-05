"""Offline HTTP relay contracts; no server sockets or device transports."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from verify_engine import CommandVerifier, VerifyResult
from web_server import WebServer


class RelayHTTP(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = Mock()
        self.auth.authenticate_token.return_value = {"id": 7, "role": "admin"}
        self.auth.get_user_devices.return_value = ["AB1"]
        self.verify = AsyncMock(
            spec=CommandVerifier(None, None).verify_command,
            return_value=(VerifyResult.ACK_ONLY, 10.0, 12.0, 2.0),
        )
        self.server = WebServer(SimpleNamespace(
            auth=self.auth, verifier=SimpleNamespace(verify_command=self.verify),
        ))

    async def request(self, payload, token="test-token"):
        self.verify.reset_mock()
        body = json.dumps(payload).encode()
        authorization = f"Authorization: Bearer {token}\r\n" if token else ""
        reader = asyncio.StreamReader()
        reader.feed_data((
            "POST /api/relay HTTP/1.1\r\nHost: gateway.local\r\n"
            f"{authorization}Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n"
        ).encode() + body)
        reader.feed_eof()
        writer = Mock(spec=["write", "drain", "close"])
        writer.drain = AsyncMock()
        await self.server._handle_client(reader, writer)
        response = b"".join(call.args[0] for call in writer.write.call_args_list)
        headers, response_body = response.split(b"\r\n\r\n", 1)
        self.assertIn(f"Content-Length: {len(response_body)}".encode(), headers)
        writer.close.assert_called_once()
        return int(headers.split()[1]), json.loads(response_body)

    async def test_action_aliases_reach_verifier_in_lowercase(self):
        for key in ("action", "s"):
            for expected, aliases in (
                ("turn_on", ("turn_on", "TURN_ON", "on", 1, "1")),
                ("turn_off", ("turn_off", "TURN_OFF", "off", 0, "0")),
            ):
                for action in aliases:
                    with self.subTest(key=key, action=action):
                        status, body = await self.request({
                            "node_id": "AB1", "channel": "ch1", key: action,
                        })
                        self.verify.assert_awaited_once_with("AB1", "ch1", expected)
                        self.assertEqual(status, 200)
                        self.assertEqual(body, {
                            "success": True, "verify": "ack_only", "node_id": "AB1",
                            "channel": "ch1", "action": expected,
                        })

    async def test_channel_aliases(self):
        for key in ("channel", "ch"):
            for expected, aliases in (("ch1", ("ch1", 1, "1")), ("ch2", ("ch2", 2, "2"))):
                for channel in aliases:
                    with self.subTest(key=key, channel=channel):
                        status, body = await self.request({
                            "node_id": "AB1", key: channel, "action": "turn_off",
                        })
                        self.verify.assert_awaited_once_with("AB1", expected, "turn_off")
                        self.assertEqual(status, 200)
                        self.assertEqual(body["channel"], expected)
                        self.assertTrue(body["success"])

    async def test_verification_outcomes_preserve_load_distinction(self):
        for result in VerifyResult:
            with self.subTest(result=result):
                self.verify.return_value = (result, 10.0, 12.0, 2.0)
                status, body = await self.request({
                    "node_id": "AB1", "channel": "ch1", "action": "turn_on",
                })
                self.assertEqual(status, 200)
                self.assertEqual(body["verify"], result.value)
                self.assertIs(body["success"], result in (
                    VerifyResult.ACK_ONLY, VerifyResult.CONFIRMED_LOAD,
                ))
                self.verify.assert_awaited_once_with("AB1", "ch1", "turn_on")

    async def test_verifier_exception_never_claims_success(self):
        for error in (TimeoutError("No ACK"), RuntimeError("Dispatch failed")):
            with self.subTest(error=error):
                self.verify.side_effect = error
                status, body = await self.request({
                    "node_id": "AB1", "channel": "ch2", "action": "turn_off",
                })
                self.assertEqual(status, 200)
                self.assertEqual(body, {"success": False, "error": str(error)})
                self.verify.assert_awaited_once_with("AB1", "ch2", "turn_off")

    async def test_invalid_action_or_channel_never_dispatches(self):
        for key, invalid in (
            ("action", ("toggle", "TURN_TOGGLE", "", None, 2, [], {})),
            ("channel", ("ch3", 0, 3, "", None, [], {})),
        ):
            for value in invalid:
                with self.subTest(key=key, value=value):
                    payload = {"node_id": "AB1", "channel": "ch1", "action": "turn_on"}
                    payload[key] = value
                    status, body = await self.request(payload)
                    self.assertEqual(status, 400)
                    self.assertIn("error", body)
                    self.verify.assert_not_called()

    async def test_missing_or_invalid_token_never_dispatches(self):
        self.auth.authenticate_token.return_value = None
        for token in (None, "invalid-token"):
            with self.subTest(token=token):
                status, body = await self.request({
                    "node_id": "AB1", "channel": "ch1", "action": "turn_on",
                }, token=token)
                self.assertEqual(status, 401)
                self.assertEqual(body["error"], "Authentication required")
                self.verify.assert_not_called()

    async def test_scoped_user_can_only_control_assigned_node(self):
        self.auth.authenticate_token.return_value = {"id": 7, "role": "user"}
        for node_id, expected_status in (("AB1", 200), ("AB2", 403)):
            with self.subTest(node_id=node_id):
                status, body = await self.request({
                    "node_id": node_id, "channel": "ch1", "action": "turn_off",
                })
                self.assertEqual(status, expected_status)
                self.auth.get_user_devices.assert_called_with(7)
                if expected_status == 200:
                    self.assertTrue(body["success"])
                    self.assertEqual(body["verify"], "ack_only")
                    self.verify.assert_awaited_once_with("AB1", "ch1", "turn_off")
                else:
                    self.assertEqual(body["error"], "Insufficient permissions")
                    self.verify.assert_not_called()


class NodeConnectionStatus(unittest.TestCase):
    def test_stale_online_records_are_not_advertised_as_connected(self):
        from datetime import datetime, timezone
        records = {
            'old': {'status': 'online', 'last_seen': '2026-01-01T00:00:00+00:00'},
            'fresh': {'status': 'online', 'last_seen': datetime.now(timezone.utc).isoformat()},
            'broken': {'status': 'online', 'last_seen': 'invalid'},
        }
        registry = SimpleNamespace(get_all_nodes=lambda: records, get_rooms=lambda: {}, get_pending=lambda: {})
        result = WebServer(SimpleNamespace(registry=registry))._nodes_snapshot()
        self.assertEqual(result['nodes']['old']['status'], 'offline')
        self.assertEqual(result['nodes']['broken']['status'], 'offline')
        self.assertEqual(result['nodes']['fresh']['status'], 'online')
        self.assertEqual(records['old']['status'], 'online')  # snapshot doesn't mutate storage


if __name__ == "__main__":
    unittest.main()
