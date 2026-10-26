"""Direct HSV V measurements from the permitted manual archive; no model refit."""
from pathlib import Path
import hashlib, io, json, shutil, zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
REPORT=ROOT/'reports/complete_thesis_report_2026-10-18'
PDF=ROOT/'output/pdf/complete_thesis_report_2026-10-18/Manual_Calibration_Complete_Thesis_Technical_Report.pdf'
ARCHIVE=Path('C:/Users/DLSU/Downloads/THESIS DATA/Data Collection/Manual Calibration (2).zip')
EXPECTED='e039dcd49f3390d34dc979490dcf46a6ecc43d9e6a2aec08e4952acc14b5006a'
SOURCE=ROOT/'reports/manual_calibration_matrices_and_light_metrics_2026-10-18/data/matched_acquisition_optical_measurements.parquet'
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
checks=[]
def check(label,passed):
    assert passed,label
    checks.append(label)

history=OUT/'preserved_report'
history.mkdir(exist_ok=True)
for p in [PDF,REPORT/'build_complete_report.py',REPORT/'report_manifest.json',REPORT/'report_validation.json',REPORT/'validate_report.py']:
    dest=history/p.name
    if not dest.exists():shutil.copy2(p,dest)
check('Manual archive hash matches allowed source',sha(ARCHIVE)==EXPECTED)
d=pd.read_parquet(SOURCE)
check('Same evaluated frame population',len(d)==8506 and d.session_id.nunique()==65 and d.frame_uid.nunique()==8506)
best=pd.read_parquet(ROOT/'reports/BEST_RESULTS/data/best_models_held_out_predictions.parquet')
best=best[best.task=='contact']
check('All frame IDs equal best-model evaluation',set(best.frame_uid)==set(d.frame_uid))
record_rows=[];sources=[]
with zipfile.ZipFile(ARCHIVE) as z:
    names={n.split('/')[-2]:n for n in z.namelist() if n.endswith('/baseline_summary.json')}
    for sid,g in d.groupby('session_id',sort=True):
        name=names[sid];raw=z.read(name);b=json.loads(raw)
        check(sid+': valid baseline',b['valid'] and b['roi_layout_id']=='roi-9fbc67c50ee3bc7145fa')
        sources.append(dict(session_id=sid,member=name,sha256=hashlib.sha256(raw).hexdigest(),baseline_id=b['baseline_id']))
        for j in range(1,10):
            x=g[f'roi{j}_mean_v'].to_numpy(float);bp=next(r for r in b['rois'] if r['roi_id']==j)
            check(sid+f': T{j} intensity bounds',np.isfinite(x).all() and (x>=0).all() and (x<=255).all())
            record_rows.append(dict(session_id=sid,group=int(g.group.iloc[0]),taxel=j,
                role=g.scientific_role.iloc[0],target_taxel=int(g.target_roi.iloc[0]),frames=len(g),
                baseline_capture_mean_v=float(bp['mean_v']),baseline_frames=int(bp['valid_frame_count']),
                mean_v=float(x.mean()),median_v=float(np.median(x)),temporal_sd_mean_v=float(x.std(ddof=1)),
                min_mean_v=float(x.min()),max_mean_v=float(x.max()),
                peak_pixel_v=float(g[f'roi{j}_max_v'].max()),
                mean_positive_delta_v=float(g[f'roi{j}_delta_v_sum_per_pixel'].mean()),
                mean_brightness_change_v=float(x.mean()-bp['mean_v'])))
r=pd.DataFrame(record_rows);r.to_csv(OUT/'v_channel_by_recording_taxel.csv',index=False)
pd.DataFrame(sources).to_csv(OUT/'baseline_source_manifest.csv',index=False)
rows=[]
for j in range(1,10):
    c=r[(r.role=='no_contact')&(r.taxel==j)]
    p=r[(r.role=='model_primary')&(r.target_taxel==j)&(r.taxel==j)]
    check(f'T{j}: support',len(c)==11 and len(p)==6)
    control=float(c.mean_v.mean());press=float(p.mean_v.mean());noise=float(np.sqrt(np.mean(c.temporal_sd_mean_v**2)))
    b=float(p.baseline_capture_mean_v.mean())
    result=dict(taxel=j,press_frames=int(p.frames.sum()),press_recordings=6,control_frames=int(c.frames.sum()),control_recordings=11,
                baseline_capture_mean_v=b,no_contact_mean_v=control,contact_mean_v=press,
                contact_median_of_recording_medians_v=float(p.median_v.median()),
                baseline_referenced_mean_change_v=float(p.mean_brightness_change_v.mean()),
                baseline_referenced_change_percent=float(np.mean(100*p.mean_brightness_change_v/p.baseline_capture_mean_v)),
                independent_control_contrast_v=press-control,
                mean_positive_delta_v=float(p.mean_positive_delta_v.mean()),
                no_contact_temporal_noise_sd_v=noise,
                contact_temporal_sd_v=float(np.sqrt(np.mean(p.temporal_sd_mean_v**2))),
                no_contact_cv_percent=100*noise/control,
                contact_min_roi_mean_v=float(p.min_mean_v.min()),contact_max_roi_mean_v=float(p.max_mean_v.max()),
                contact_peak_pixel_v=float(p.peak_pixel_v.max()),contact_mean_encoding_percent=100*press/255)
    check(f'T{j}: baseline contrast identity',np.isclose(result['baseline_referenced_mean_change_v'],press-b,atol=1e-12))
    # Independent direct-frame calculation verifies recording weights.
    original=d[(d.scientific_role=='model_primary')&(d.target_roi==j)]
    w=1/original.groupby('session_id').session_id.transform('size')
    check(f'T{j}: weighted raw mean independent calculation',np.isclose(np.average(original[f'roi{j}_mean_v'],weights=w),press,atol=1e-12))
    rows.append(result)
summary=pd.DataFrame(rows);summary.to_csv(OUT/'v_channel_metrics_by_taxel.csv',index=False)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
fig,axes=plt.subplots(2,2,figsize=(9,8),layout='constrained')
panels=[('no_contact_mean_v','No-contact mean raw V','viridis',25,29,'V levels'),
        ('contact_mean_v','Contact mean raw V','viridis',25,29,'V levels'),
        ('baseline_referenced_mean_change_v','Change from own baseline mean','RdBu_r',None,None,'Signed V levels'),
        ('no_contact_temporal_noise_sd_v','No-contact temporal noise','magma',0,None,'SD of ROI mean V')]
for ax,(key,title,cmap,lo,hi,label) in zip(axes.flat,panels):
    values=summary[key].to_numpy().reshape(3,3)
    if key=='baseline_referenced_mean_change_v':hi=float(np.max(abs(values)));lo=-hi
    if hi is None:hi=float(values.max())*1.12
    im=ax.imshow(values,vmin=lo,vmax=hi,cmap=cmap)
    ax.set_title(title,fontweight='bold',fontsize=11,pad=10);ax.set_xticks([]);ax.set_yticks([])
    for ii in range(3):
        for jj in range(3):
            v=values[ii,jj];rgba=plt.get_cmap(cmap)((v-lo)/(hi-lo));lum=.2126*rgba[0]+.7152*rgba[1]+.0722*rgba[2]
            ax.text(jj,ii,f'T{ii*3+jj+1}\n{v:.3f}',ha='center',va='center',color='black' if lum>.55 else 'white',fontsize=12)
    fig.colorbar(im,ax=ax,fraction=.044,pad=.035,label=label)
fig.savefig(OUT/'v_channel_heatmaps.png',dpi=250);fig.savefig(OUT/'v_channel_heatmaps.svg');plt.close(fig)
result={'source_parquet':str(SOURCE),'source_parquet_sha256':sha(SOURCE),'archive_sha256':EXPECTED,
        'baseline_sources':65,'baseline_capture_frames_range':[int(r.baseline_frames.min()),int(r.baseline_frames.max())],
        'definitions':{'raw_v':'ROI mean of HSV V in 0-255 encoding',
            'baseline':'Saved baseline_summary mean_v: mean across baseline pixels and baseline frames',
            'change':'Mean raw V during eligible contact minus that recording\'s baseline-capture mean V; signed, not clipped',
            'noise':'RMS of within-recording sample SD of raw ROI mean V across 11 no-contact recordings',
            'aggregation':'Equal recordings: six target-press records/taxel; 11 no-contact records/taxel',
            'positive_delta':'Existing mean positive per-pixel baseline difference, a separate statistic'},
        'metrics':rows,'checks':checks,'check_count':len(checks)}
(OUT/'v_channel_metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(summary[['taxel','baseline_capture_mean_v','no_contact_mean_v','contact_mean_v','baseline_referenced_mean_change_v','no_contact_temporal_noise_sd_v','contact_peak_pixel_v']].to_string(index=False))
print('Checks:',len(checks))
