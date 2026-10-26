from pathlib import Path
import hashlib, json
base=Path(__file__).resolve().parent
manifest=json.loads((base/'release_parts.json').read_text(encoding='utf-8'))
destination=base/manifest['archive']
if destination.exists(): raise SystemExit('Destination already exists; move it before reassembling.')
for part in manifest['parts']:
    p=base/part['name']
    if not p.is_file() or p.stat().st_size!=part['bytes']: raise SystemExit('Missing or wrong-size part: '+part['name'])
temporary=destination.with_name(destination.name+'.assembling')
if temporary.exists(): raise SystemExit('A partial .assembling file exists; move or remove it before retrying.')
whole=hashlib.sha256()
with temporary.open('xb') as out:
    for part in manifest['parts']:
        h=hashlib.sha256()
        with (base/part['name']).open('rb') as src:
            while data:=src.read(8*1024*1024): out.write(data); h.update(data); whole.update(data)
        if h.hexdigest()!=part['sha256']: raise SystemExit('Checksum mismatch: '+part['name'])
        print('Verified '+part['name'],flush=True)
if whole.hexdigest()!=manifest['sha256'] or temporary.stat().st_size!=manifest['bytes']: raise SystemExit('Combined ZIP verification failed')
temporary.rename(destination)
print('Complete and verified: '+str(destination))
