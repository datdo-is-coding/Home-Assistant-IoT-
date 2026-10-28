"""Verify archived bytes and symlink targets without running archived code."""
import hashlib
import json
import os
from pathlib import Path


def main():
    base = Path(__file__).resolve().parent
    root = base.parent.parent
    manifest = json.loads((base / 'manifest.json').read_text())
    count = total = 0
    for record in manifest['records']:
        if record['kind'] != 'archived':
            continue
        relative = Path(record['destination'])
        assert not relative.is_absolute() and '..' not in relative.parts
        folder = root / relative
        assert folder.is_relative_to(base / 'files')
        for entry in record['entries']:
            relative = Path(entry['path'])
            assert not relative.is_absolute() and '..' not in relative.parts
            path = folder / relative
            if entry['type'] == 'symlink':
                assert path.is_symlink() and os.readlink(path) == entry['target'], path
            elif entry['type'] == 'directory':
                assert path.is_dir() and not path.is_symlink(), path
            else:
                assert path.is_file() and not path.is_symlink(), path
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                        digest.update(chunk)
                assert path.stat().st_size == entry['size'], path
                assert digest.hexdigest() == entry['sha256'], path
                count += 1
                total += entry['size']
    print(f'Verified {count} archived files, {total} bytes; symlink targets intact.')


if __name__ == '__main__':
    main()
