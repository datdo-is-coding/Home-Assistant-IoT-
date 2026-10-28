"""Unit tests for WebServer and Gateway security features (Wi-Fi lock, Cookies, Voice Vocabulary scoping)."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from web_server import WebServer
from main import SmartHomeGateway


class WebServerSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = Mock()
        self.auth.has_any_admin.return_value = True
        self.auth.authenticate_token.return_value = {"id": 1, "username": "admin", "role": "admin"}
        self.auth.login = Mock(return_value={"success": True, "token": "session-tok-123"})
        self.auth.logout = Mock()
        self.auth.get_user_devices.return_value = ["node1"]

        self.gateway = SimpleNamespace(
            auth=self.auth,
            is_commissioning=False,
            get_voice_vocabulary_diagnostics=Mock(return_value={"success": True, "scoped": True})
        )
        self.server = WebServer(self.gateway)

    async def _send_request(self, method: str, path: str, headers: dict = None, body: bytes = b""):
        req_headers = {
            "Host": "gateway.local",
            "Content-Length": str(len(body)),
        }
        if headers:
            req_headers.update(headers)

        header_lines = "".join(f"{k}: {v}\r\n" for k, v in req_headers.items())
        raw_req = f"{method} {path} HTTP/1.1\r\n{header_lines}\r\n".encode() + body

        reader = asyncio.StreamReader()
        reader.feed_data(raw_req)
        reader.feed_eof()

        writer = Mock(spec=["write", "drain", "close"])
        writer.drain = AsyncMock()

        await self.server._handle_client(reader, writer)
        raw_response = b"".join(call.args[0] for call in writer.write.call_args_list)
        if not raw_response:
            return 0, {}, b""

        parts = raw_response.split(b"\r\n\r\n", 1)
        resp_headers_raw = parts[0].decode()
        resp_body = parts[1] if len(parts) > 1 else b""

        first_line = resp_headers_raw.split("\r\n")[0]
        status = int(first_line.split()[1])

        parsed_headers = {}
        for line in resp_headers_raw.split("\r\n")[1:]:
            if ": " in line:
                k, v = line.split(": ", 1)
                parsed_headers[k.lower()] = v

        return status, parsed_headers, resp_body

    async def test_downloads_use_current_homecompetition_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Gateway/gateway').mkdir(parents=True)
            apk = root / 'releases/android/HomeCompetition.apk'
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b'current HomeCompetition APK')
            with patch('web_server.__file__', str(root / 'Gateway/gateway/web_server.py')):
                for method in ('GET', 'HEAD'):
                    status, headers, body = await self._send_request(method, '/api/app/download')
                    self.assertEqual(status, 200)
                    self.assertEqual(int(headers['content-length']), apk.stat().st_size)
                    self.assertIn('HomeCompetition.apk', headers['content-disposition'])
                    self.assertEqual(body, apk.read_bytes() if method == 'GET' else b'')

    async def test_test_speak_does_not_claim_success_when_only_synthesis_works(self):
        self.gateway.audio_server = SimpleNamespace(speak_proactive=AsyncMock(return_value=False))
        self.gateway.tts = SimpleNamespace(synthesize_pcm=AsyncMock(return_value=b'pcm'))
        status, _, body = await self._send_request('POST', '/api/proactive/test_speak',
                                                  headers={'Authorization': 'Bearer test-admin'}, body=b'{}')
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)['success'])
        self.gateway.tts.synthesize_pcm.assert_not_awaited()

    async def test_wifi_connect_unauthenticated_blocked_when_provisioned(self):
        """Unauthenticated requests to /api/wifi/connect are rejected with 401 when admin exists."""
        self.auth.has_any_admin.return_value = True
        status, _, body = await self._send_request(
            "POST", "/api/wifi/connect",
            body=json.dumps({"ssid": "OfficeWiFi", "password": "pass"}).encode()
        )
        self.assertEqual(status, 401)
        data = json.loads(body)
        self.assertEqual(data.get("error"), "Authentication required")

    @patch("asyncio.create_subprocess_exec")
    async def test_wifi_connect_unauthenticated_allowed_when_unprovisioned(self, mock_exec):
        """Unauthenticated requests to /api/wifi/connect succeed if no admin is set up yet (commissioning)."""
        self.auth.has_any_admin.return_value = False
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        status, _, body = await self._send_request(
            "POST", "/api/wifi/connect",
            body=json.dumps({"ssid": "FreshSetupAP", "password": "pass"}).encode()
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("success"))
        self.assertIn("FreshSetupAP", data.get("message", ""))
        await asyncio.sleep(0)

    async def test_wifi_connect_member_forbidden(self):
        """Non-admin (member) role is forbidden (403) from calling /api/wifi/connect."""
        self.auth.has_any_admin.return_value = True
        self.auth.authenticate_token.return_value = {"id": 2, "username": "member1", "role": "member"}

        status, _, body = await self._send_request(
            "POST", "/api/wifi/connect",
            headers={"Authorization": "Bearer member-token"},
            body=json.dumps({"ssid": "OfficeWiFi", "password": "pass"}).encode()
        )
        self.assertEqual(status, 403)

    @patch("asyncio.create_subprocess_exec")
    async def test_wifi_connect_admin_allowed(self, mock_exec):
        """Admin is allowed to reconfigure Wi-Fi."""
        self.auth.has_any_admin.return_value = True
        self.auth.authenticate_token.return_value = {"id": 1, "username": "admin", "role": "admin"}
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        status, _, body = await self._send_request(
            "POST", "/api/wifi/connect",
            headers={"Authorization": "Bearer admin-token"},
            body=json.dumps({"ssid": "OfficeWiFi", "password": "pass"}).encode()
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("success"))
        await asyncio.sleep(0)

    async def test_login_cookie_omits_secure_on_plain_http(self):
        """Over direct plain HTTP LAN, Set-Cookie must not have Secure attribute so cookies work on HTTP."""
        status, headers, _ = await self._send_request(
            "POST", "/api/auth/login",
            body=json.dumps({"username": "admin", "password": "secret"}).encode()
        )
        self.assertEqual(status, 200)
        set_cookie = headers.get("set-cookie", "")
        self.assertIn("aetheria_session=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertNotIn("Secure", set_cookie)

    async def test_login_cookie_includes_secure_when_forwarded_https(self):
        """When behind reverse proxy with X-Forwarded-Proto: https, Set-Cookie must include Secure."""
        status, headers, _ = await self._send_request(
            "POST", "/api/auth/login",
            headers={"X-Forwarded-Proto": "https"},
            body=json.dumps({"username": "admin", "password": "secret"}).encode()
        )
        self.assertEqual(status, 200)
        set_cookie = headers.get("set-cookie", "")
        self.assertIn("aetheria_session=", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertIn("HttpOnly", set_cookie)

    async def test_logout_cookie_omits_secure_on_plain_http(self):
        """Logout cookie over plain HTTP must not specify Secure."""
        status, headers, _ = await self._send_request(
            "POST", "/api/auth/logout",
            headers={"Authorization": "Bearer admin-token"}
        )
        self.assertEqual(status, 200)
        set_cookie = headers.get("set-cookie", "")
        self.assertIn("Max-Age=0", set_cookie)
        self.assertNotIn("Secure", set_cookie)

    async def test_logout_cookie_includes_secure_on_https(self):
        """Logout cookie over HTTPS must include Secure."""
        status, headers, _ = await self._send_request(
            "POST", "/api/auth/logout",
            headers={"Authorization": "Bearer admin-token", "X-Forwarded-Proto": "https"}
        )
        self.assertEqual(status, 200)
        set_cookie = headers.get("set-cookie", "")
        self.assertIn("Max-Age=0", set_cookie)
        self.assertIn("Secure", set_cookie)

    async def test_voice_vocabulary_endpoint_passes_user_context(self):
        """GET /api/voice/vocabulary passes current_user to get_voice_vocabulary_diagnostics."""
        member_user = {"id": 5, "username": "member5", "role": "member"}
        self.auth.authenticate_token.return_value = member_user

        status, _, body = await self._send_request(
            "GET", "/api/voice/vocabulary",
            headers={"Authorization": "Bearer member-token"}
        )
        self.assertEqual(status, 200)
        self.gateway.get_voice_vocabulary_diagnostics.assert_called_once_with(user=member_user)


class VoiceVocabularyScopingLogicTests(unittest.TestCase):
    def setUp(self):
        self.nodes = {
            "node_admin_only": {
                "mac": "11:22:33:44:55:66",
                "room": "kho",
                "channels": {
                    "ch1": {"name": "Đèn kho", "device_type": "light", "aliases": ["den kho"]}
                }
            },
            "node_shared": {
                "mac": "AA:BB:CC:DD:EE:FF",
                "room": "phong_khach",
                "channels": {
                    "ch1": {"name": "Đèn chùm", "device_type": "light", "aliases": ["den chum"]}
                }
            }
        }
        self.registry = Mock()
        self.registry.get_all_nodes.return_value = self.nodes
        self.registry.get_rooms.return_value = {"kho": {}, "phong_khach": {}}

        def mock_get_user_accessible_nodes(user):
            if not user or user.get("role") == "admin":
                return self.nodes
            if user.get("id") == 2:
                return {"node_shared": self.nodes["node_shared"]}
            return {}

        self.registry.get_user_accessible_nodes.side_effect = mock_get_user_accessible_nodes

        self.asr = Mock()
        self.asr.dump_active_vocabulary.return_value = {
            "initialized": True,
            "hotwords_count": 2,
            "hotwords": ["BẬT ĐÈN KHO", "TẮT ĐÈN CHÙM"]
        }

        self.gw = SmartHomeGateway.__new__(SmartHomeGateway)
        self.gw.registry = self.registry
        self.gw.asr = self.asr

    def test_admin_receives_unscoped_vocabulary(self):
        admin_user = {"id": 1, "role": "admin"}
        result = self.gw.get_voice_vocabulary_diagnostics(user=admin_user)
        self.assertTrue(result["success"])
        stored_device_ids = [d["device_id"] for d in result["stored_vocabulary"]]
        self.assertIn("node_admin_only::ch1", stored_device_ids)
        self.assertIn("node_shared::ch1", stored_device_ids)
        self.assertEqual(len(result["stt_engine"]["hotwords"]), 2)

    def test_member_receives_scoped_vocabulary_and_hotwords(self):
        member_user = {"id": 2, "role": "member"}
        result = self.gw.get_voice_vocabulary_diagnostics(user=member_user)
        self.assertTrue(result["success"])
        stored_device_ids = [d["device_id"] for d in result["stored_vocabulary"]]
        self.assertNotIn("node_admin_only::ch1", stored_device_ids)
        self.assertIn("node_shared::ch1", stored_device_ids)
        # Hotword for admin-only node ("BẬT ĐÈN KHO") must be filtered out for member!
        self.assertEqual(result["stt_engine"]["hotwords"], ["TẮT ĐÈN CHÙM"])
        self.assertEqual(result["stt_engine"]["hotwords_count"], 1)

    def test_unassigned_member_receives_empty_device_vocabulary(self):
        unassigned_user = {"id": 99, "role": "member"}
        result = self.gw.get_voice_vocabulary_diagnostics(user=unassigned_user)
        self.assertTrue(result["success"])
        self.assertEqual(result["stored_vocabulary"], [])
        self.assertEqual(result["stt_engine"]["hotwords"], [])
        self.assertEqual(result["stt_engine"]["hotwords_count"], 0)


if __name__ == "__main__":
    unittest.main()
