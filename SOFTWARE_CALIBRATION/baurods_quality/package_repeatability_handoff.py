"""Package the revised report and traceable statistical evidence after PDF review."""
from pathlib import Path
import csv, hashlib, json, zipfile

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent
DEST=ROOT/'thesis_handoff'
OUT=ROOT/'outputs'
NEW=OUT/'repeatability_20261018'
PDF=WORK/'output/pdf'
STEM='BAURods_Manual_Calibration_Technical_Report'
review=json.loads((PDF/'repeatability_pdf_verification.json').read_text())
assert review['visual_inspection']=='passed'
assert review['pdf_sha256']==hashlib.sha256((PDF/f'{STEM}.pdf').read_bytes()).hexdigest()
report=(DEST/f'{STEM}.md').read_text(encoding='utf-8')
assert report==(DEST/f'{STEM}.txt').read_text(encoding='utf-8')
check=json.loads((DEST/'handoff_verification.json').read_text())
check.update(version='1.1',revision_date='2026-10-18',report_words=len(report.split()),
             original_source_table_count=35,source_table_count=48,original_figure_pairs=15,figure_pairs=19,
             pdf_pages=review['pages'],report_sha256=hashlib.sha256(report.encode()).hexdigest(),
             statistical_supplement='Repeatability, conditional force adjustment, approximate uncertainty; no pass/fail judgment',
             physical_press_replicates_known=False,independent_sessions=1)
(DEST/'handoff_verification.json').write_text(json.dumps(check,indent=2),encoding='utf-8')
(DEST/'README.md').write_text('''# Manual calibration thesis handoff - version 1.1

Revised 18 October 2026. Upload the PDF under output/pdf, or the same full narrative in BAURods_Manual_Calibration_Technical_Report.txt. Paste ChatGPT_Writing_Prompt.txt as the writing brief. Later trained-model work remains in its separate report.

The revised PDF preserves the original audit and adds Part VIII: recording-level repeatability, approximate confidence intervals, a force-adjusted model, diagnostics and sensitivity analyses. No acceptance limit or pass/fail judgment is assigned. The main model uses all 72 press-designated recordings, one per taxel and TEST-group cell. There is only one source session. TEST groups are matched labels, not established independent temporal blocks. No physical-press independence is inferred.

The evidence contains 35 original and 13 supplemental CSV tables, 15 original and 4 supplemental PNG/SVG figure pairs, numerical scripts, validation receipts and a file-hash manifest. The PDF contains 12 selected figures and 20 tables. The supplement's evidence is under outputs/repeatability_20261018. The original ZIP and model artifacts are not included. No original acquisition or model-training file was modified.

The executed numerical script is repeatability_analysis.py. Run it using the analysis environment in calibration_gui/.venv. It rereads the original ZIP and requires its original location, available in outputs/summary.json. Run build_repeatability_supplement.py after it to update the full Markdown/text handoff. If rebuilding the original audit narrative using build_technical_handoff.py, run build_repeatability_supplement.py afterward to restore the statistical revision. Build the PDF with thesis_handoff/create_pdf_report.py in the bundled document Python environment (ReportLab, Pillow and pypdf). Run validate_repeatability_pdf.py, review its rendered pages, record the review status, and then run package_repeatability_handoff.py.

The original report was preserved locally under thesis_handoff/history/20261005_v1_0 and is intentionally omitted from this latest-version package. The numerical analysis was executed as a Python script; this revision does not claim execution of a Jupyter notebook. The older interactive report and initial data-quality package document the original audit; the revised PDF and this handoff are the sources for the added statistics.
''',encoding='utf-8')

files=[p for p in DEST.iterdir() if p.is_file() and p.name!='PACKAGE_MANIFEST.csv']
files+=list((OUT/'tables').glob('*.csv'))+list((OUT/'figures').glob('*.png'))+list((OUT/'figures').glob('*.svg'))
files += [OUT/n for n in ['summary.json','validation_checks.json','supplemental_validation.json','delivery_verification.json','analysis.log']]
files += [ROOT/n for n in ['data_quality_analysis.py','supplemental_audit.py','build_report.py','build_technical_handoff.py','requirements.txt','README.md','Data_Quality_Report.md','Thesis_Data_Quality_Assessment.md','repeatability_analysis.py','build_repeatability_supplement.py','validate_repeatability_pdf.py','package_repeatability_handoff.py']]
files += [p for p in NEW.rglob('*') if p.is_file()]
files += [PDF/f'{STEM}.pdf',PDF/'pdf_build_verification.json',PDF/'repeatability_pdf_verification.json']
files=sorted(set(files))
assert all(p.exists() for p in files)
manifest=DEST/'PACKAGE_MANIFEST.csv'
with manifest.open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f);w.writerow(['path_relative_to_workspace','bytes','sha256'])
    for p in files:w.writerow([p.relative_to(WORK).as_posix(),p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()])
files.append(manifest)
archive=WORK/'BAURods_Manual_Calibration_Thesis_Handoff.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6,strict_timestamps=False) as z:
    for p in files:z.write(p,p.relative_to(WORK).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(files)
print(json.dumps({'package':str(archive),'files':len(files),'bytes':archive.stat().st_size,'pdf_pages':review['pages'],'pdf_sha256':review['pdf_sha256']},indent=2))
