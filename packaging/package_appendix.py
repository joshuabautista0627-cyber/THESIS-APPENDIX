import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
EXTERNAL = Path(r'C:\Users\DLSU\Downloads\THESIS DATA\Data Collection')
ZIP = OUT / 'SPARE_Thesis_Appendix_2026-10-19.zip'
SKIP = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'tmp', '.mplconfig', '.codex-slide-sensor-metrics-20260818', 'thesis_appendix_package'}
blocked, excluded, rows = [], [], []
files = []
def error(e):
    blocked.append(Path(e.filename).relative_to(ROOT).as_posix())
for d, dirs, names in os.walk(ROOT, onerror=error):
    for name in dirs[:]:
        if name in SKIP:
            dirs.remove(name)
            excluded.append((Path(d) / name).relative_to(ROOT).as_posix() + '/')
    for name in names:
        p = Path(d) / name
        if name == '.env' or name.startswith('.env.') and name not in {'.env.example', '.env.sample'} or name in {'credentials.json', 'id_rsa'} or p.suffix in {'.pem', '.key', '.pfx'}:
            excluded.append(p.relative_to(ROOT).as_posix())
            continue
        files.append((p, 'SOFTWARE_CALIBRATION/' + p.relative_to(ROOT).as_posix(), 'current workspace'))
for p in sorted(EXTERNAL.iterdir()):
    if p.is_file():
        files.append((p, 'Original_Data_Archives/' + p.name, 'external source file'))

commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
tree = subprocess.check_output(['git','ls-tree','-r','-z',commit], cwd=ROOT)
recovered = []
for entry in tree.split(b'\0'):
    if not entry: continue
    meta, path = entry.split(b'\t', 1)
    mode, kind, oid = meta.decode().split()
    rel = path.decode('utf-8')
    if kind == 'blob' and any(rel.startswith(b + '/') for b in blocked):
        recovered.append((rel, oid))
unresolved = [b for b in blocked if not any(r.startswith(b + '/') for r, _ in recovered)]
print(f'Packaging {len(files)} current files; {len(recovered)} files recovered from commit {commit}; unresolved folders: {unresolved}', flush=True)

def add_stream(z, arc, src, origin, expected=None):
    digest = hashlib.sha256(); size = 0
    info = zipfile.ZipInfo(arc)
    info.compress_type = zipfile.ZIP_STORED if Path(arc).suffix.lower() in {'.zip','.mp4','.avi','.png','.jpg','.jpeg','.pdf','.gz','.pptx','.docx'} else zipfile.ZIP_DEFLATED
    info.date_time = datetime.now().timetuple()[:6]
    with z.open(info, 'w', force_zip64=True) as dest:
        while True:
            chunk = src.read(min(4*1024*1024, expected-size) if expected is not None else 4*1024*1024)
            if not chunk: break
            dest.write(chunk); digest.update(chunk); size += len(chunk)
            if expected is not None and size == expected: break
    if expected is not None and size != expected: raise RuntimeError('Truncated source: '+arc)
    rows.append({'path':arc,'bytes':size,'sha256':digest.hexdigest(),'source':origin})

with zipfile.ZipFile(ZIP, 'w', allowZip64=True, compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for i, (p, arc, origin) in enumerate(files):
        before = p.stat()
        with p.open('rb') as src: add_stream(z, arc, src, origin)
        after = p.stat()
        if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns): raise RuntimeError('Source changed during packaging: '+str(p))
        if i % 500 == 0 or before.st_size > 100_000_000: print(f'Added {i+1}/{len(files)}: {arc}', flush=True)
    proc = subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    for rel, oid in recovered:
        proc.stdin.write((oid+'\n').encode()); proc.stdin.flush()
        header = proc.stdout.readline().decode().split()
        if len(header)!=3 or header[1]!='blob': raise RuntimeError(str(header))
        add_stream(z, 'SOFTWARE_CALIBRATION/'+rel, proc.stdout, 'Git commit '+commit, int(header[2]))
        if proc.stdout.read(1)!=b'\n': raise RuntimeError('Git stream separator missing')
    proc.stdin.close(); proc.wait()
    manifest = io.StringIO(newline=''); writer = csv.DictWriter(manifest,fieldnames=['path','bytes','sha256','source']); writer.writeheader();writer.writerows(rows)
    z.writestr('FILE_MANIFEST.csv',manifest.getvalue())
    report = {'git_commit_for_recovered_files':commit,'recovered_files':[r for r,_ in recovered],'access_denied_directories':blocked,'unresolved_directories':unresolved,'excluded_paths':excluded,'external_source_directory':str(EXTERNAL),'external_subdirectories_not_duplicated':[p.name for p in EXTERNAL.iterdir() if p.is_dir()]}
    z.writestr('PACKAGING_NOTES.json',json.dumps(report,indent=2))
    readme = f'''# SPARE thesis appendix archive

Prepared 19 October 2026 (Asia/Manila). This is a source and evidence snapshot, not a new validation of scientific results or hardware operation.

## Contents
- SOFTWARE_CALIBRATION: SPARE GUI source, force/localization models, Arduino firmware, configurations, tests, dependency lists, accessible recordings, processed datasets, analysis scripts, reports, figures, notebooks, and existing handoff packages.
- Original_Data_Archives: original ZIP archives and companion files from the Data Collection directory. Existing extracted data subdirectories are not duplicated; raw data is supplied in its original archives. Historical archive versions are included.
- FILE_MANIFEST.csv: path, byte count, SHA-256, and source of each payload file.
- PACKAGING_NOTES.json: exact exclusions, inaccessible folders, and recovered file paths.

## Snapshot provenance and limitations
{len(recovered)} files under {len(blocked)} inaccessible workspace directories were recovered from Git commit {commit}. They occupy their normal project paths so model and dataset references remain usable. Their manifest source explicitly identifies Git. These are committed historical copies; their equality to the inaccessible current files could not be checked. Accessible working files include uncommitted changes. This is therefore a mixed snapshot, not a clean checkout of a single commit.

Unresolved inaccessible directories: {json.dumps(unresolved)}.

Installed virtual environments, dependency caches, temporary working folders, Git metadata/history, and credential filenames are excluded. The supplied dependency requirements support reinstalling packages. Existing report drafts and historical results remain intact and should not automatically be treated as the final thesis conclusions.

## Run the SPARE application
Extract the ZIP to a local folder with sufficient free space. In SOFTWARE_CALIBRATION/calibration_gui, follow README.md and setup_windows.bat. The documented environment is Windows with Python 3.11 or later. Install requirements.txt into a new virtual environment, then launch app.py --simulation for a hardware-free starting point. Hardware operation requires the wiring, calibration, and port configuration in the project README and hardware checklist.

Analysis dependencies are listed in requirements-analysis.txt and the lock files. BAURods analysis has its own README and requirements.txt. Some analysis scripts contain original absolute data paths; point their archive arguments to Original_Data_Archives after extraction. Rebuilding the report web app may require its documented Data plugin runtime.

## Appendix use
Refer to this ZIP as electronic supplementary material and identify the archive filename and its companion SHA-256 checksum in the thesis. FILE_MANIFEST.csv supports checking individual payloads. The archive documents the supplied implementation and evidence; it does not independently prove scientific accuracy or authorship. Packaging did not rerun experiments, train models, or operate hardware.
'''
    z.writestr('README_THESIS_APPENDIX.md',readme)
    z.write(__file__, 'packaging/package_appendix.py')
(OUT/'README_THESIS_APPENDIX.md').write_text(readme,encoding='utf-8')
(OUT/'PACKAGING_NOTES.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Verifying all ZIP entries and payload SHA-256 values...',flush=True)
with zipfile.ZipFile(ZIP) as z:
    by_path={r['path']:r for r in rows}
    for i,info in enumerate(z.infolist()):
        h=hashlib.sha256()
        with z.open(info) as src:
            while chunk:=src.read(4*1024*1024): h.update(chunk)
        if info.filename in by_path and h.hexdigest()!=by_path[info.filename]['sha256']: raise RuntimeError('Hash mismatch: '+info.filename)
        if i%1000==0: print(f'Verified {i+1} entries',flush=True)
print('Computing ZIP checksum...',flush=True)
with ZIP.open('rb') as src: archive_hash=hashlib.file_digest(src,'sha256').hexdigest()
(OUT/(ZIP.name+'.sha256')).write_text(archive_hash+'  '+ZIP.name+'\n',encoding='utf-8')
verification={'archive':ZIP.name,'bytes':ZIP.stat().st_size,'payload_files':len(rows),'recovered_from_git':len(recovered),'unresolved_directories':unresolved,'all_entry_crc_and_payload_sha256_checks':'passed','sha256':archive_hash}
(OUT/'verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
print(json.dumps(verification,indent=2),flush=True)
