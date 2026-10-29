#!/usr/bin/env python3
"""Publish Android metadata only after verifying the public GitHub APK download."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gateway'))
from firebase_commissioning import AdminStore, read_config


def verify_download(manifest):
    expected = {'schema', 'package', 'version', 'version_code', 'size', 'sha256', 'url'}
    if set(manifest) != expected or manifest['schema'] != 1:
        raise ValueError('Invalid release manifest')
    if manifest['package'] != 'com.dtv.homeassistant.dtv_home_assistant':
        raise ValueError('Wrong application package')
    if (not isinstance(manifest['version'], str) or
            not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?', manifest['version']) or
            type(manifest['version_code']) is not int or manifest['version_code'] <= 0 or
            type(manifest['size']) is not int or not 1024 <= manifest['size'] <= 120 * 1024 * 1024 or
            not re.fullmatch('[0-9a-f]{64}', str(manifest['sha256']))):
        raise ValueError('Invalid release version, size or digest')
    url = ('https://github.com/datdo-is-coding/Home-Assistant-IoT-/releases/download/'
           f'app-v{manifest["version"]}/HomeCompetition.apk')
    if manifest['url'] != url:
        raise ValueError('APK must belong to this repository release')
    digest = hashlib.sha256()
    size = 0
    with requests.get(url, stream=True, timeout=(15, 45)) as response:
        response.raise_for_status()
        final = urlsplit(response.url)
        if final.scheme != 'https' or final.hostname not in ('github.com', 'release-assets.githubusercontent.com'):
            raise ValueError('Untrusted APK redirect')
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > manifest['size']:
                raise ValueError('Published APK is larger than expected')
            digest.update(chunk)
    if size != manifest['size'] or digest.hexdigest() != manifest['sha256']:
        raise ValueError('Published APK size/hash mismatch')


async def publish(config, manifest):
    await asyncio.to_thread(verify_download, manifest)
    store = AdminStore(read_config(config))
    rules = (await store.rules())['rules']['app_releases']['android']['stable']
    if rules != {'.read': 'auth != null', '.write': False}:
        raise ValueError('Deploy the reviewed app release Rules before publishing')
    path = 'app_releases/android/stable'
    previous = await store.read(path)
    if previous:
        if previous['version_code'] > manifest['version_code']:
            raise ValueError('Refusing a release downgrade')
        if previous['version_code'] == manifest['version_code'] and previous != manifest:
            raise ValueError('A version code cannot be reused with a different artifact')
    await store.write(path, manifest)
    if await store.read(path) != manifest:
        raise RuntimeError('Firebase release verification failed')
    print(json.dumps({'published': True, **manifest}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firebase-config', required=True)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(publish(args.firebase_config, json.loads(args.manifest.read_text())))


if __name__ == '__main__':
    main()
