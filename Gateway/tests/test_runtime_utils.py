"""Offline regression tests; no database, audio device, or cloud access."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))

from registry_manager import canon_device, slug
import tts_engine


class RegistryNamesTests(unittest.TestCase):
    def test_vietnamese_names(self):
        cases = {
            "  ĐÈN phòng ngủ  ": "den_phong_ngu",
            "ẤẮẴẶỀỄỈỘỚỰỸ": "aaaaeeioouy",
            "phong-khach_node01": "phong_khach_node01",
            "": "unknown",
            "___": "unknown",
            "💡": "unknown",
            None: "unknown",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(slug(value), expected)

    def test_device_aliases(self):
        self.assertEqual(canon_device("BÓNG ĐÈN"), "light")
        self.assertEqual(canon_device("máy bơm"), "pump")
        self.assertEqual(canon_device("custom device"), "custom_device")


class TTSStreamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Only exercise streaming; avoid constructing caches or local models.
        self.engine = tts_engine.TTSEngine.__new__(tts_engine.TTSEngine)
        self.engine.voice = "primary"
        self.engine.fallback_voice = "fallback"

    async def test_chunks_keep_order_and_return_immutable_bytes(self):
        async def stream():
            yield {"type": "WordBoundary", "text": "ignored"}
            for chunk in (b"RIFF", b"", b"\x00\x01", b"audio"):
                yield {"type": "audio", "data": chunk}

        communicate = Mock(return_value=SimpleNamespace(stream=stream))
        with patch.object(tts_engine, "HAS_EDGE_TTS", True), patch.object(
            tts_engine, "edge_tts", SimpleNamespace(Communicate=communicate)
        ):
            result = await self.engine.synthesize_edgetts("Xin chào!", "4%", "2Hz")
        self.assertIs(type(result), bytes)
        self.assertEqual(result, b"RIFF\x00\x01audio")
        communicate.assert_called_once_with("Xin chào.", "primary", rate="+4%", pitch="+2Hz")

    async def test_retry_discards_partial_audio(self):
        async def failed_stream():
            yield {"type": "audio", "data": b"partial"}
            raise RuntimeError("interrupted")

        async def recovered_stream():
            yield {"type": "audio", "data": b"complete"}

        communicate = Mock(side_effect=[
            SimpleNamespace(stream=failed_stream),
            SimpleNamespace(stream=recovered_stream),
        ])
        with patch.object(tts_engine, "HAS_EDGE_TTS", True), patch.object(
            tts_engine, "edge_tts", SimpleNamespace(Communicate=communicate)
        ), patch.object(tts_engine.asyncio, "sleep", new_callable=AsyncMock):
            result = await self.engine.synthesize_edgetts("Xin chào")
        self.assertEqual(result, b"complete")
        self.assertEqual(communicate.call_args_list[-1].args[1], "fallback")

    async def test_unavailable_provider(self):
        with patch.object(tts_engine, "HAS_EDGE_TTS", False):
            self.assertIsNone(await self.engine.synthesize_edgetts("Xin chào"))


if __name__ == "__main__":
    unittest.main()
