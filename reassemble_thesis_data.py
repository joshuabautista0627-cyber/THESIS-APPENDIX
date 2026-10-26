"""Verify and join the complete THESIS DATA release. Requires Python 3.8+."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

def reassemble(base, output_directory=None, verify_only=False):
    base = Path(base)
    manifest = json.loads((base / 'thesis_data_parts.json').read_text(encoding='utf-8'))
    archive_name = manifest['archive']
    names = [p['name'] for p in manifest['parts']]
    if not names or len(names) != len(set(names)):
        raise ValueError('Manifest has missing or duplicate parts')
    for name in [archive_name, *names]:
        if Path(name).name != name or name in {'.', '..'} or '/' in name or '\\' in name:
            raise ValueError('Manifest contains an unsafe filename')
    if sum(p['bytes'] for p in manifest['parts']) != manifest['bytes']:
        raise ValueError('Manifest part sizes do not match the archive size')
    for part in manifest['parts']:
        source = base / part['name']
        if not source.is_file() or source.stat().st_size != part['bytes']:
            raise ValueError('Missing or wrong-size part: ' + part['name'])
    destination = Path(output_directory or base) / archive_name
    temporary = destination.with_name(destination.name + '.assembling')
    if not verify_only and (destination.exists() or temporary.exists()):
        raise FileExistsError('Output or .assembling file already exists; move it before retrying')
    output = None if verify_only else temporary.open('xb')
    combined = hashlib.sha256()
    total = 0
    try:
        for part in manifest['parts']:
            digest = hashlib.sha256()
            with (base / part['name']).open('rb') as source:
                while True:
                    data = source.read(8 * 1024 * 1024)
                    if not data:
                        break
                    digest.update(data)
                    combined.update(data)
                    total += len(data)
                    if output is not None:
                        output.write(data)
            if digest.hexdigest() != part['sha256']:
                raise ValueError('Checksum mismatch: ' + part['name'])
            print('Verified ' + part['name'], flush=True)
    finally:
        if output is not None:
            output.close()
    if combined.hexdigest() != manifest['sha256'] or total != manifest['bytes']:
        raise ValueError('Combined archive checksum or size does not match')
    if verify_only:
        print('All parts and combined archive checksum verified.')
    else:
        temporary.rename(destination)
        print('Complete and verified: ' + str(destination))
    return destination

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parts-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output-dir', type=Path, help='Existing directory for the reconstructed ZIP')
    parser.add_argument('--verify-only', action='store_true', help='Verify downloads without creating the ZIP')
    args = parser.parse_args()
    try:
        reassemble(args.parts_dir, args.output_dir, args.verify_only)
    except (ValueError, OSError, KeyError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
