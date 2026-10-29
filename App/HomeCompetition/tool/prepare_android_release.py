#!/usr/bin/env python3
"""Verify the built APK and prepare the Firebase release catalog (no credentials)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = 'com.dtv.homeassistant.dtv_home_assistant'
CERTIFICATE = '7bccf31712aa03d76bfc27c36fa5e31a84d70fa5daaa73ba4ce6f2e904b1a603'


def prepare(apk, sdk):
    folders = [p for p in (sdk / 'build-tools').iterdir() if (p / 'aapt').is_file()]
    tools = max(folders, key=lambda p: tuple(map(int, re.findall(r'\d+', p.name))))
    badging = subprocess.check_output([str(tools / 'aapt'), 'dump', 'badging', str(apk)], text=True)
    match = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging)
    if not match or match[1] != PACKAGE:
        raise ValueError('APK package does not match HomeCompetition')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?', match[3]):
        raise ValueError('Invalid release version')
    certs = subprocess.check_output([str(tools / 'apksigner'), 'verify', '--print-certs', str(apk)], text=True)
    actual = re.findall(r'certificate SHA-256 digest: ([0-9a-f]{64})', certs)
    if actual != [CERTIFICATE]:
        raise ValueError('APK signer does not match installed HomeCompetition')
    size = apk.stat().st_size
    if not 1024 <= size <= 120 * 1024 * 1024:
        raise ValueError('APK size is outside update limits')
    with apk.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return {'schema': 1, 'package': PACKAGE, 'version': match[3],
            'version_code': int(match[2]), 'size': size,
            'sha256': digest,
            'url': f'https://github.com/datdo-is-coding/Home-Assistant-IoT-/releases/download/app-v{match[3]}/HomeCompetition.apk'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT / 'releases/android/HomeCompetition.apk')
    parser.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME', str(Path.home() / 'Android/Sdk'))))
    parser.add_argument('--output', type=Path, default=ROOT / 'releases/android/release.json')
    args = parser.parse_args()
    manifest = prepare(args.apk, args.sdk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(manifest, indent=2) + '\n')
    temporary.replace(args.output)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
