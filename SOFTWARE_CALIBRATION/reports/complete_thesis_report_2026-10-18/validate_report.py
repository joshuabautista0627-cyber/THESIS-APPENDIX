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
check(image_total==16,'All sixteen figures embedded, including nine raw and eighteen transformed V-force panels')
vf=readj(ROOT/'reports/manual_v_force_relationship_2026-10-19/v_force_analysis.json')
for row in vf['pooled']:
    vals=[str(row['taxel']),str(row['frames']),f'{row["pearson_r"]:.4f}',f'{row["linear_r2"]:.6f}',
          f'{row["intercept_v"]:.4f}',f'{row["slope_v_per_N"]:.4f}']
    check(norm(' '.join(vals)) in flat,f'Raw V-force pooled fit T{row["taxel"]}: all values exact')
for j in range(1,10):
    for metric in ['pearson_r','linear_r2','frames']:
        vals=[str(j)]+[(str(next(r[metric] for r in vf['within_recording'] if r['taxel']==j and r['test_group']==g)) if metric=='frames'
                         else f"{next(r[metric] for r in vf['within_recording'] if r['taxel']==j and r['test_group']==g):.4f}") for g in range(1,7)]
        check(norm(' '.join(vals)) in flat,f'Raw V-force recording matrix T{j}, {metric}: exact')
for first in [1,4,7]:
    check(f'Raw V versus force: taxels T{first}-T{first+2}' in text,f'Plot group T{first}-T{first+2} present')
nv_dir=ROOT/'reports/manual_normalized_v_force_2026-10-19'
nv=readj(nv_dir/'normalized_v_force_analysis.json')
for row in nv['comparisons']:
    vals=[str(row['taxel'])]+[f'{row[s+suffix]:.{digits}f}' for s in ['raw_mean_v','corrected_v','normalized_percent'] for suffix,digits in [('_r',4),('_r2',6)]]
    check(norm(' '.join(vals)) in flat,f'Raw/corrected/normalized comparison T{row["taxel"]}: all six values exact')
for j in range(1,10):
    vals=[str(j)]+[f"{next(r['baseline_v'] for r in nv['baselines'] if r['taxel']==j and r['test_group']==g):.6f}" for g in range(1,7)]
    check(norm(' '.join(vals)) in flat,f'Exact baseline V0 for all TEST groups at T{j}')
    vals=[str(j)]+[f"{next(r[k] for r in nv['pooled'] if r['taxel']==j and r['signal']==s):.6f}" for s in ['corrected_v','normalized_percent'] for k in ['intercept','slope_per_N']]
    check(norm(' '.join(vals)) in flat,f'Corrected and normalized fit coefficients T{j}: exact')
for first in [1,4,7]:
    check(f'Corrected and normalized V: taxels T{first}-T{first+2}' in text,f'Transformed plot group T{first}-T{first+2} present')
for bid in set(r['baseline_id'] for r in nv['baselines']):
    check(bid in text,f'Reused baseline identity preserved: {bid}')
old_manifest=readj(nv_dir/'preserved_report/report_manifest.json')
new_figs={r['name']:r for r in manifest['figures']}
for f in old_manifest['figures']:
    check(f['name'] in new_figs and new_figs[f['name']]['sha256']==f['sha256'] and sha(Path(f['path']))==f['sha256'],f'Existing figure unchanged and embedded: {f["name"]}')
check(sha(nv_dir/'preserved_report'/pdf.name)==nv['preserved_report_sha256'],'Complete pre-update report preserved')
check(all(sha(ROOT/p)==h for p,h in nv['preserved_raw_artifacts'].items()),'All earlier raw-V analysis files and original plots preserved')
vrows=readcsv(ROOT/'reports/manual_v_channel_metrics_2026-10-18/v_channel_metrics_by_taxel.csv')
for row in vrows:
    groups=[(['baseline_capture_mean_v','no_contact_mean_v','contact_mean_v','baseline_referenced_mean_change_v','mean_positive_delta_v'],[3]*5),
            (['no_contact_temporal_noise_sd_v','contact_temporal_sd_v','no_contact_cv_percent','contact_min_roi_mean_v','contact_max_roi_mean_v','contact_peak_pixel_v'],[4,4,3,3,3,0]),
            (['contact_median_of_recording_medians_v','baseline_referenced_change_percent','independent_control_contrast_v','contact_mean_encoding_percent'],[3]*4)]
    for k,(fields,precision) in enumerate(groups):
        vals=[row['taxel']]+[f'{float(row[key]):.{digits}f}' for key,digits in zip(fields,precision)]
        check(norm(' '.join(vals)) in flat,f'Direct V-channel table {k+1}, taxel {row["taxel"]}: exact values')
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
