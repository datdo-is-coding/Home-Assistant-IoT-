import asyncio
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location(
    'android_release_publisher', Path(__file__).resolve().parents[1] / 'tools/publish_android_catalog.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class AndroidReleasePublishTests(unittest.TestCase):
    def manifest(self):
        return {'schema': 1, 'package': 'com.dtv.homeassistant.dtv_home_assistant',
                'version': '1.7.0', 'version_code': 43, 'size': 1024,
                'sha256': hashlib.sha256(b'a' * 1024).hexdigest(),
                'url': 'https://github.com/datdo-is-coding/Home-Assistant-IoT-/releases/download/app-v1.7.0/HomeCompetition.apk'}

    def response(self, body):
        response = MagicMock()
        response.__enter__.return_value = response
        response.url = 'https://release-assets.githubusercontent.com/asset.apk'
        response.iter_content.return_value = iter([body])
        return response

    def test_checks_the_actual_download_digest(self):
        with patch.object(publisher.requests, 'get', return_value=self.response(b'a' * 1024)):
            publisher.verify_download(self.manifest())
        with patch.object(publisher.requests, 'get', return_value=self.response(b'b' * 1024)):
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                publisher.verify_download(self.manifest())

    def test_rejects_another_repository_before_download(self):
        with patch.object(publisher.requests, 'get') as get:
            with self.assertRaises(ValueError):
                publisher.verify_download({**self.manifest(), 'url': 'https://github.com/other/repo/update.apk'})
            get.assert_not_called()

    def test_rejects_reusing_a_version_or_downgrading_before_writing(self):
        manifest = self.manifest()
        class Store:
            async def rules(self):
                return {'rules': {'app_releases': {'android': {'stable': {
                    '.read': 'auth != null', '.write': False}}}}}
            async def read(self, _): return self.previous
            async def write(self, *_): raise AssertionError('must not write')
        for previous in [{**manifest, 'version_code': 44}, {**manifest, 'sha256': 'b' * 64}]:
            store = Store(); store.previous = previous
            with patch.object(publisher, 'verify_download'), \
                    patch.object(publisher, 'read_config', return_value={}), \
                    patch.object(publisher, 'AdminStore', return_value=store):
                with self.assertRaises(ValueError):
                    asyncio.run(publisher.publish('unused', manifest))


if __name__ == '__main__':
    unittest.main()
