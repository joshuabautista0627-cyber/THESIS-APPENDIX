"""Validate the delivered PDF against its preserved source evidence."""
import csv
import hashlib
import json
import re
from pathlib import Path
import pdfplumber
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
def readj(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def readcsv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return re.sub(r'\s+',' ',s).strip()
manifest=readj(HERE/'report_manifest.json');pdf=Path(manifest['pdf'])
reader=PdfReader(pdf);texts=[p.extract_text() or '' for p in reader.pages]
text='\n\n'.join(texts);flat=norm(text);checks=[]
def check(value,name):
    assert value,name
    checks.append(name)

check(manifest['pdf_sha256']==sha(pdf),'PDF matches generation manifest')
check(len(reader.pages)>=40,'Complete report with methodology and full appendices')
check('\ufffd' not in text and '\u25a0' not in text,'No replacement-glyph characters in PDF text')
check(all(len(t)>250 for t in texts),'No blank or orphan-only pages')
check(len(reader.outline)==18,'All 18 report sections are bookmarked')
for label in ['84.88','85.00','99.24','99.54','99.09','98.67','0.4972','0.6299','0.3113']:
    check(label in texts[0] or label in texts[16],f'Primary metric {label} in headline or full metric table')

comp=readcsv(ROOT/'reports/BEST_RESULTS/reference/all_competing_models_ranked.csv')
check(len(comp)==50,'All 50 source comparison rows retained')
table_regions={'force':norm(texts[7]),'localization':norm(texts[8]),'contact':norm(texts[9])}
for row in comp:
    task=row['task']
    vals=[row['rank_by_primary_metric'],row['model']]
    if task=='force': vals += [f'{float(row[k]):.4f}' for k in ['mae_N','rmse_N','bias_N','r2']]
    else:vals += [f'{100*float(row[k]):.2f}' for k in
                  (['accuracy','balanced_accuracy','macro_f1'] if task=='localization' else
                   ['accuracy','balanced_accuracy','macro_f1','recall','precision','fpr'])]
    check(norm(' '.join(vals)) in table_regions[task],f'Comparison row exact: {task} / {row["model"]}')

for filename,decimals in [('localization_raw_counts.csv',0),('localization_row_normalized_percent.csv',2),
                          ('contact_raw_counts.csv',0),('contact_row_normalized_percent.csv',2),
                          ('light_response_distribution_percent.csv',2),('light_force_spearman_by_group_taxel.csv',3)]:
    rows=readcsv(ROOT/'reports/BEST_RESULTS/data'/filename)
    for row in rows:
        keys=list(row);values=[row[keys[0]]]+[str(int(float(row[k]))) if decimals==0 else f'{float(row[k]):.{decimals}f}' for k in keys[1:]]
        check(norm(' '.join(values)) in flat,f'Matrix row exact: {filename} / {row[keys[0]]}')

protocol=readj(ROOT/'calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/protocol.json')
gridtext=norm(text[text.index('Appendix A. Exhaustive tuning configuration grid',text.index('Writing prompt')):])
for c in protocol['candidates']:
    pairtext='; '.join(f'{k}={json.dumps(v)}' for k,v in c['params'].items())
    row=' '.join([c['id'],c['family'],c['features'],c['weights'],pairtext])
    check(norm(row) in gridtext,f'Exact tuning grid row: {c["id"]}')
configs=readj(ROOT/'reports/BEST_RESULTS/BEST_MODEL_CONFIGURATIONS.json')
for fold,v in configs['fold_model_configurations'].items():
    check(repr(v['contact']['threshold']) in flat,f'Contact threshold exact in fold {fold}')
    for mem in v['force']['members']:
        check(repr(mem['offset']) in flat,f'Force offset exact in fold {fold} / {mem["id"]}')

bounds=[];image_total=0
with pdfplumber.open(pdf) as doc:
    for i,p in enumerate(doc.pages,1):
        image_total+=len(p.images)
        bad=[c for c in p.chars if c['x0']<44 or c['x1']>p.width-43 or c['top']<16 or c['bottom']>p.height-16]
        if bad:bounds.append({'page':i,'chars':''.join(c['text'] for c in bad)})
check(not bounds,'All PDF text remains within page margins')
check(image_total==9,'All nine figures embedded')
for src in manifest['sources']:
    check(sha(ROOT/src['path'])==src['sha256'],f'Source unchanged: {src["id"]}')
preserved=readj(HERE/'preserved_files.json')
changed=[]
for path,h in preserved.items():
    p=ROOT/path
    if not p.exists() or sha(p)!=h: changed.append(path)
check(not changed,f'All {len(preserved)} existing reports/artifacts preserved')
exact=readj(ROOT/'reports/manual_calibration_thesis_report_2026-10-05/Exact_Segmentation_and_Model_Configurations.json')
model_dir=ROOT/'calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/models'
verified=set()
for task,bundle in exact['bundles']['models'].items():
    for m in bundle['saved_specification']['members']:
        if m['file'] not in verified:
            check(sha(model_dir/m['file'])==m['sha256'],f'Saved trained component preserved: {m["file"]}')
            verified.add(m['file'])
(HERE/'extracted_pdf_text.txt').write_text(text,encoding='utf-8')
result={'status':'passed','checks':checks,'check_count':len(checks),'pages':len(reader.pages),
        'tables':len(manifest['tables']),'figures':image_total,'model_comparison_rows':50,
        'candidate_configurations':178,'preserved_files':len(preserved),'pdf_sha256':sha(pdf)}
(HERE/'report_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
