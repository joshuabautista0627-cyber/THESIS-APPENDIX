"""Compare signed baseline correction and relative normalization on fixed manual frames."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, json, shutil, zipfile
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
REPORT=ROOT/'reports/complete_thesis_report_2026-10-18'
PRIOR=ROOT/'reports/manual_v_force_relationship_2026-10-19'
V_DIR=ROOT/'reports/manual_v_channel_metrics_2026-10-18'
ARCHIVE=Path('C:/Users/DLSU/Downloads/THESIS DATA/Data Collection/Manual Calibration (2).zip')
PDF=ROOT/'output/pdf/complete_thesis_report_2026-10-18/Manual_Calibration_Complete_Thesis_Technical_Report.pdf'
CHECKS=[]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(label,valid):
    assert valid,label
    CHECKS.append(label)
def readj(p):return json.loads(p.read_text(encoding='utf-8'))

history=OUT/'preserved_report';history.mkdir(exist_ok=True)
for p in [PDF]+[REPORT/n for n in ['build_complete_report.py','validate_report.py','report_manifest.json','report_validation.json']]:
    dest=history/p.name
    if not dest.exists():shutil.copy2(p,dest)
preserved={str(p.relative_to(ROOT)):sha(p) for p in PRIOR.iterdir() if p.is_file()}
prior=readj(PRIOR/'v_force_analysis.json')
v=readj(V_DIR/'v_channel_metrics.json')
check('Original allowed manual archive hash',sha(ARCHIVE)==v['archive_sha256'])
check('Original optical measurements unchanged',sha(Path(prior['source']))==prior['source_sha256'])
check('Best held-out model predictions unchanged',sha(ROOT/'reports/BEST_RESULTS/data/best_models_held_out_predictions.parquet')==prior['best_predictions_sha256'])
points=pd.read_parquet(PRIOR/'v_force_plotted_points.parquet')
optical=pd.read_parquet(prior['source']);optical=optical[optical.scientific_role=='model_primary']
check('Same 7154 frames, 54 records and nine taxels',len(points)==7154 and points.frame_uid.nunique()==7154 and points.session_id.nunique()==54 and points.taxel.nunique()==9)
check('Frame identities equal original eligible manual optical rows',set(points.frame_uid)==set(optical.frame_uid))
for t,g in points.groupby('taxel'):
    orig=optical.set_index('frame_uid').loc[g.frame_uid]
    check(f'T{t}: exact original force and raw V',np.array_equal(g.reference_force_N,orig.reference_force_N) and np.array_equal(g.raw_mean_v,orig[f'roi{t}_mean_v']))
manifest=pd.read_csv(V_DIR/'baseline_source_manifest.csv').set_index('session_id')
baseline_rows=[]
with zipfile.ZipFile(ARCHIVE) as z:
    for (sid,t),g in points.groupby(['session_id','taxel']):
        m=manifest.loc[sid];raw=z.read(m.member);b=json.loads(raw)
        bp=next(r for r in b['rois'] if r['roi_id']==t)
        value=float(bp['mean_v'])
        check(f'{sid}: baseline JSON hash and layout',hashlib.sha256(raw).hexdigest()==m.sha256 and b['valid'] and b['roi_layout_id']=='roi-9fbc67c50ee3bc7145fa')
        check(f'{sid}: finite positive baseline denominator',np.isfinite(value) and value>0 and bp['valid_frame_count']>0)
        record_start=datetime.strptime('_'.join(sid.split('_')[:3]),'%Y-%m-%d_%H%M%S_%f').replace(tzinfo=timezone(timedelta(hours=8)))
        baseline_time=datetime.fromisoformat(b['capture_timestamp_iso'])
        check(f'{sid}: saved baseline predates recording',baseline_time<record_start)
        baseline_rows.append(dict(session_id=sid,taxel=int(t),test_group=int(g.group.iloc[0]),baseline_v=value,
            baseline_frames=int(bp['valid_frame_count']),baseline_id=b['baseline_id'],capture_timestamp_iso=b['capture_timestamp_iso'],
            member=m.member,sha256=m.sha256))
baselines=pd.DataFrame(baseline_rows)
check('Three saved baseline captures represented',baselines.baseline_id.nunique()==3 and baselines.sha256.nunique()==3)
points=points.merge(baselines[['session_id','taxel','baseline_v']],on=['session_id','taxel'],validate='many_to_one')
points['corrected_v']=points.raw_mean_v-points.baseline_v
points['normalized_percent']=100*points.corrected_v/points.baseline_v
check('No transformations remove or duplicate frames',len(points)==7154 and np.isfinite(points[['raw_mean_v','corrected_v','normalized_percent']]).all().all())

def fit(x,y,w):
    x,y,w=np.asarray(x,float),np.asarray(y,float),np.asarray(w,float)
    w=w/w.sum();xm=np.sum(w*x);ym=np.sum(w*y);dx=x-xm;dy=y-ym
    xx=np.sum(w*dx*dx);yy=np.sum(w*dy*dy);xy=np.sum(w*dx*dy)
    assert xx>0 and yy>0
    slope=xy/xx;intercept=ym-slope*xm;r=xy/np.sqrt(xx*yy)
    residual=y-intercept-slope*x;r2=1-np.sum(w*residual**2)/yy
    return dict(pearson_r=float(r),linear_r2=float(r2),intercept=float(intercept),slope_per_N=float(slope),
                fit_rmse=float(np.sqrt(np.sum(w*residual**2))))

signals=['raw_mean_v','corrected_v','normalized_percent']
pooled=[];recordings=[];comparisons=[]
for t,g in points.groupby('taxel',sort=True):
    w=g.recording_weight.to_numpy();x=g.reference_force_N.to_numpy()
    check(f'T{t}: equal recording weights retained',np.allclose(g.groupby('session_id').recording_weight.sum(),1))
    row={'taxel':int(t),'frames':len(g),'recordings':6}
    for signal in signals:
        y=g[signal].to_numpy();m=fit(x,y,w)
        coef=np.linalg.lstsq(np.column_stack([np.ones(len(x)),x])*np.sqrt(w[:,None]),y*np.sqrt(w),rcond=None)[0]
        cov=np.cov(x,y,aweights=w,ddof=0)
        check(f'T{t} {signal}: independent weighted least squares and Pearson',np.allclose(coef,[m['intercept'],m['slope_per_N']],atol=1e-10) and np.isclose(m['pearson_r'],cov[0,1]/np.sqrt(cov[0,0]*cov[1,1]),atol=1e-12))
        check(f'T{t} {signal}: R2 equals r squared',np.isclose(m['linear_r2'],m['pearson_r']**2,atol=1e-12))
        pooled.append(dict(taxel=int(t),signal=signal,frames=len(g),recordings=6,**m))
        row[signal+'_r']=m['pearson_r'];row[signal+'_r2']=m['linear_r2']
    old=next(m for m in prior['pooled'] if m['taxel']==t)
    check(f'T{t}: raw benchmark exactly reproduced',np.allclose([row['raw_mean_v_r'],row['raw_mean_v_r2']],[old['pearson_r'],old['linear_r2']],atol=1e-12))
    row['corrected_r2_change']=row['corrected_v_r2']-row['raw_mean_v_r2']
    row['normalized_r2_change']=row['normalized_percent_r2']-row['raw_mean_v_r2']
    row['highest_pooled_r2_signal']=max(signals,key=lambda s:row[s+'_r2'])
    comparisons.append(row)
    for sid,s in g.groupby('session_id'):
        metrics={signal:fit(s.reference_force_N,s[signal],np.ones(len(s))) for signal in signals}
        for signal,m in metrics.items():
            recordings.append(dict(taxel=int(t),test_group=int(s.group.iloc[0]),session_id=sid,signal=signal,frames=len(s),**m))
            check(f'{sid} {signal}: independent within-record Pearson',np.isclose(pearsonr(s.reference_force_N,s[signal]).statistic,m['pearson_r'],atol=1e-12))
        check(f'{sid}: affine correction preserves within-record r and R2',all(np.allclose([m['pearson_r'],m['linear_r2']],[metrics['raw_mean_v']['pearson_r'],metrics['raw_mean_v']['linear_r2']],atol=1e-12) for m in metrics.values()))

pd.DataFrame(pooled).to_csv(OUT/'pooled_signal_metrics.csv',index=False)
pd.DataFrame(recordings).to_csv(OUT/'within_recording_signal_metrics.csv',index=False)
pd.DataFrame(comparisons).to_csv(OUT/'signal_comparison_by_taxel.csv',index=False)
baselines.to_csv(OUT/'baseline_provenance.csv',index=False)
baselines.pivot(index='taxel',columns='test_group',values='baseline_v').to_csv(OUT/'baseline_v_by_taxel_and_test.csv')
points.to_parquet(OUT/'normalized_v_force_points.parquet',index=False)

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10.5,'axes.spines.top':False,'axes.spines.right':False,
    'axes.edgecolor':'#657580','axes.labelcolor':'#14314A','text.color':'#14314A','svg.fonttype':'none','figure.facecolor':'white'})
colors={1:'#0072B2',2:'#B58A00',3:'#7B61A8',4:'#587D39',5:'#BD5C9D',6:'#D2691E'}
markers={1:'o',2:'s',3:'^',4:'v',5:'D',6:'P'}
legend=[Line2D([],[],color=colors[g],marker=markers[g],linestyle='none',markersize=5,label=f'TEST{g}') for g in range(1,7)]
legend.append(Line2D([],[],color='#182E40',lw=1.6,linestyle='--',label='Weighted linear fit'))
figures=[]
for first in [1,4,7]:
    fig,axes=plt.subplots(3,2,figsize=(7.2,8.35),sharex=True,sharey='col')
    fig.subplots_adjust(left=.10,right=.985,top=.835,bottom=.07,hspace=.50,wspace=.36)
    fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.53,.995),ncol=4,frameon=False,fontsize=8.8,columnspacing=1.2)
    fig.text(.30,.915,'Baseline-corrected V',ha='center',fontsize=12,fontweight='bold')
    fig.text(.79,.915,'Normalized V',ha='center',fontsize=12,fontweight='bold')
    for row,t in enumerate(range(first,first+3)):
        g=points[points.taxel==t]
        for col,signal in enumerate(['corrected_v','normalized_percent']):
            ax=axes[row,col];m=next(m for m in pooled if m['taxel']==t and m['signal']==signal)
            for group in range(1,7):
                s=g[g.group==group]
                ax.scatter(s.reference_force_N,s[signal],s=8,alpha=.5,color=colors[group],marker=markers[group],linewidths=0)
            xl=np.array([g.reference_force_N.min(),g.reference_force_N.max()])
            ax.plot(xl,m['intercept']+m['slope_per_N']*xl,'--',color='#182E40',lw=1.6)
            ax.axhline(0,color='#75838F',lw=.6)
            ax.set_title(f"T{t}   r = {m['pearson_r']:+.4f}\nR² = {m['linear_r2']:.6f}   n = {len(g):,}",fontsize=10.4,fontweight='bold',loc='left',pad=7)
            ax.set_ylabel('V - V₀ (V levels)' if col==0 else '100 × (V - V₀) / V₀ (%)',fontsize=9.4)
            ax.set(xlim=(0,3.05),xticks=[0,1,2,3],ylim=(-2,5.3) if col==0 else (-7,17),yticks=[-2,0,2,4] if col==0 else [-5,0,5,10,15])
            ax.grid(lw=.4,color='#DDE3E8');ax.set_axisbelow(True);ax.tick_params(labelsize=9)
            if row==2:ax.set_xlabel('Aligned reference force (N)',fontsize=9.5)
    stem=f'normalized_v_force_taxels_{first}_{first+2}'
    fig.savefig(OUT/(stem+'.png'),dpi=300);fig.savefig(OUT/(stem+'.svg'));plt.close(fig)
    figures.append(dict(stem=stem,taxels=list(range(first,first+3))))

for path,h in preserved.items():check('Prior raw-V artifact preserved: '+path,sha(ROOT/path)==h)
summary={'date':'2026-10-19','source_archive':str(ARCHIVE),'source_archive_sha256':v['archive_sha256'],
    'source_points_sha256':sha(PRIOR/'v_force_plotted_points.parquet'),'prior_analysis_sha256':sha(PRIOR/'v_force_analysis.json'),
    'scope':{'frames':7154,'recordings':54,'taxels':9,'test_groups':6,'force_interval_N':[.05,3]},
    'method':{'baseline':'Associated saved baseline_summary.json ROI mean_v, mean across baseline pixels and frames; three captures reused across 54 recordings',
        'corrected':'V - V0, signed camera V levels; no clipping',
        'normalized':'100 * (V - V0) / V0, percent change relative to the associated saved baseline',
        'weight':'1/n_s per frame, equal total weight for each of six recordings per taxel',
        'fit':'signal_hat = intercept + slope * aligned reference force; weighted least squares with intercept',
        'r2':'1 - weighted SSE / weighted signal variance = weighted Pearson r squared; descriptive in-sample association',
        'scope_limits':'Same 7154 points and alignment as raw-V analysis; no force-informed normalization, smoothing, filtering, retuning or model refit',
        'invariance':'Within a recording, subtraction and positive scaling preserve Pearson r and intercept-fit R2; V/V0 and percent relative change also have identical r and R2'},
    'pooled':pooled,'within_recording':recordings,'comparisons':comparisons,'baselines':baseline_rows,
    'baseline_capture_count':3,'figures':figures,'checks':CHECKS,'check_count':len(CHECKS),
    'preserved_raw_artifacts':preserved,'preserved_report_sha256':sha(history/PDF.name)}
(OUT/'normalized_v_force_analysis.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(pd.DataFrame(comparisons).to_string(index=False))
print(baselines.groupby(['baseline_id','capture_timestamp_iso']).agg(records=('session_id','size'),tests=('test_group',lambda s:sorted(s.unique())),frames=('baseline_frames','first')).to_string())
print('Checks:',len(CHECKS))
