"""Raw V against aligned force, with equal-recording descriptive linear fits."""
from pathlib import Path
import hashlib,json,shutil
import numpy as np
import pandas as pd
from scipy.stats import pearsonr,linregress
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
REPORT=ROOT/'reports/complete_thesis_report_2026-10-18'
SOURCE=ROOT/'reports/manual_calibration_matrices_and_light_metrics_2026-10-18/data/matched_acquisition_optical_measurements.parquet'
PRED=ROOT/'reports/BEST_RESULTS/data/best_models_held_out_predictions.parquet'
PDF=ROOT/'output/pdf/complete_thesis_report_2026-10-18/Manual_Calibration_Complete_Thesis_Technical_Report.pdf'
CHECKS=[]
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(name,condition):
    assert condition,name
    CHECKS.append(name)

# Save the current complete document and its authored sources before changing it.
history=OUT/'preserved_report';history.mkdir(exist_ok=True)
for path in [PDF]+[REPORT/n for n in ['build_complete_report.py','validate_report.py','report_manifest.json','report_validation.json']]:
    dest=history/path.name
    if not dest.exists():shutil.copy2(path,dest)
v_source=json.loads((ROOT/'reports/manual_v_channel_metrics_2026-10-18/v_channel_metrics.json').read_text(encoding='utf-8'))
check('Optical source unchanged from verified manual-V analysis',sha(SOURCE)==v_source['source_parquet_sha256'])
best_manifest=json.loads((REPORT/'report_manifest.json').read_text(encoding='utf-8'))
check('Best held-out predictions retain source hash',sha(PRED)==next(s['sha256'] for s in best_manifest['sources'] if s['id']=='S3'))
optical=pd.read_parquet(SOURCE)
d=optical[optical.scientific_role=='model_primary'].copy()
p=pd.read_parquet(PRED);p=p[p.task=='force']
check('All eligible manual positives retained',len(d)==7154 and d.session_id.nunique()==54 and not d.frame_uid.duplicated().any())
check('No frame subset or additional rejection',set(d.frame_uid)==set(p.frame_uid))
joined=d[['frame_uid','reference_force_N','target_roi','group']].merge(
    p[['frame_uid','truth','target_roi','outer_fold']],on='frame_uid',validate='one_to_one',suffixes=('_optical','_prediction'))
check('Aligned force is unchanged',np.allclose(joined.reference_force_N,joined.truth,atol=0,rtol=0))
check('Taxel and group labels agree',joined.target_roi_optical.eq(joined.target_roi_prediction).all() and joined.group.eq(joined.outer_fold).all())
check('Force interval remains 0.05-3 N inclusive',d.reference_force_N.between(.05,3).all())

def fit(x,y,w):
    x,y,w=np.asarray(x,float),np.asarray(y,float),np.asarray(w,float)
    w=w/w.sum();xm=np.sum(w*x);ym=np.sum(w*y);dx=x-xm;dy=y-ym
    xx=np.sum(w*dx*dx);yy=np.sum(w*dy*dy);xy=np.sum(w*dx*dy)
    assert xx>0 and yy>0
    b=xy/xx;a=ym-b*xm;r=xy/np.sqrt(xx*yy)
    residual=y-a-b*x;r2=1-np.sum(w*residual**2)/yy
    return dict(pearson_r=float(r),linear_r2=float(r2),intercept_v=float(a),slope_v_per_N=float(b),
                mean_force_N=float(xm),mean_raw_v=float(ym),fit_rmse_v=float(np.sqrt(np.sum(w*residual**2))))

pooled=[];recordings=[];scatter=[]
for taxel in range(1,10):
    g=d[d.target_roi==taxel].copy().sort_values(['session_id','capture_monotonic_relative_s'])
    x=g.reference_force_N.to_numpy(float);y=g[f'roi{taxel}_mean_v'].to_numpy(float)
    weights=1/g.groupby('session_id').session_id.transform('size').to_numpy()
    check(f'T{taxel}: six complete recordings',g.session_id.nunique()==6 and set(g.group)==set(range(1,7)))
    check(f'T{taxel}: finite raw V within encoding',np.isfinite(y).all() and (y>=0).all() and (y<=255).all())
    check(f'T{taxel}: equal recording weights',np.allclose(pd.Series(weights,index=g.index).groupby(g.session_id).sum(),1))
    m=fit(x,y,weights)
    beta=np.linalg.lstsq(np.column_stack([np.ones(len(x)),x])*np.sqrt(weights[:,None]),y*np.sqrt(weights),rcond=None)[0]
    check(f'T{taxel}: independent weighted least-squares coefficients',np.allclose(beta,[m['intercept_v'],m['slope_v_per_N']],atol=1e-10))
    cov=np.cov(x,y,aweights=weights,ddof=0)
    check(f'T{taxel}: independent weighted correlation',np.isclose(m['pearson_r'],cov[0,1]/np.sqrt(cov[0,0]*cov[1,1]),atol=1e-12))
    check(f'T{taxel}: in-sample intercept-fit R2 equals Pearson r squared',np.isclose(m['linear_r2'],m['pearson_r']**2,atol=1e-12))
    pooled.append(dict(taxel=taxel,frames=len(g),recordings=6,**m))
    for sid,s in g.groupby('session_id'):
        xx=s.reference_force_N.to_numpy(float);yy=s[f'roi{taxel}_mean_v'].to_numpy(float)
        mm=fit(xx,yy,np.ones(len(s)));scipyfit=linregress(xx,yy)
        check(f'T{taxel} / TEST{int(s.group.iloc[0])}: independent Pearson and linear fit',
            np.isclose(pearsonr(xx,yy).statistic,mm['pearson_r'],atol=1e-12) and
            np.allclose([scipyfit.intercept,scipyfit.slope],[mm['intercept_v'],mm['slope_v_per_N']],atol=1e-10))
        recordings.append(dict(taxel=taxel,test_group=int(s.group.iloc[0]),session_id=sid,frames=len(s),**mm))
    ss=g[['frame_uid','session_id','group','capture_monotonic_relative_s','reference_force_N']].copy()
    ss['taxel']=taxel;ss['raw_mean_v']=y;ss['recording_weight']=weights
    scatter.append(ss)
pool=pd.DataFrame(pooled);rec=pd.DataFrame(recordings);points=pd.concat(scatter,ignore_index=True)
pool.to_csv(OUT/'v_force_by_taxel.csv',index=False);rec.to_csv(OUT/'v_force_by_recording.csv',index=False)
points.to_parquet(OUT/'v_force_plotted_points.parquet',index=False)
for metric,filename in [('pearson_r','within_recording_pearson_r.csv'),('linear_r2','within_recording_linear_r2.csv'),('frames','within_recording_support.csv')]:
    rec.pivot(index='taxel',columns='test_group',values=metric).to_csv(OUT/filename)

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10.5,'axes.spines.top':False,'axes.spines.right':False,
                     'axes.edgecolor':'#657580','axes.labelcolor':'#14314A','text.color':'#14314A',
                     'svg.fonttype':'none','figure.facecolor':'white'})
COLORS={1:'#0072B2',2:'#B58A00',3:'#7B61A8',4:'#587D39',5:'#BD5C9D',6:'#D2691E'}
MARKERS={1:'o',2:'s',3:'^',4:'v',5:'D',6:'P'}
legend=[Line2D([],[],color=COLORS[g],marker=MARKERS[g],linestyle='none',markersize=5,label=f'TEST{g}') for g in range(1,7)]
legend.append(Line2D([],[],color='#182E40',lw=1.6,linestyle='--',label='Weighted linear fit'))
figures=[]
for start in [1,4,7]:
    fig,axes=plt.subplots(3,1,figsize=(7.2,8.35),sharex=True,sharey=True)
    fig.subplots_adjust(left=.11,right=.98,top=.87,bottom=.075,hspace=.40)
    fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.53,.99),ncol=4,frameon=False,fontsize=9,columnspacing=1.25)
    for ax,taxel in zip(axes,range(start,start+3)):
        g=points[points.taxel==taxel];m=pooled[taxel-1]
        for group in range(1,7):
            s=g[g.group==group]
            ax.scatter(s.reference_force_N,s.raw_mean_v,s=10,alpha=.5,color=COLORS[group],marker=MARKERS[group],linewidths=0)
        xline=np.array([g.reference_force_N.min(),g.reference_force_N.max()])
        ax.plot(xline,m['intercept_v']+m['slope_v_per_N']*xline,'--',color='#182E40',lw=1.6)
        ax.set_title(f"T{taxel}    Pearson r = {m['pearson_r']:+.4f}    R² = {m['linear_r2']:.6f}    n = {m['frames']:,}",
                     fontsize=11,fontweight='bold',loc='left',pad=9)
        ax.set_ylabel('Raw mean V\n(0-255 encoding)',fontsize=10)
        ax.set(xlim=(0,3.05),ylim=(24.5,36.8),xticks=np.arange(0,3.1,.5),yticks=[25,28,31,34,36])
        ax.grid(axis='both',lw=.4,color='#DDE3E8');ax.set_axisbelow(True)
        ax.tick_params(labelsize=9)
    axes[-1].set_xlabel('Aligned reference force (N)',fontsize=11)
    stem=f'v_force_taxels_{start}_{start+2}'
    fig.savefig(OUT/(stem+'.png'),dpi=300);fig.savefig(OUT/(stem+'.svg'));plt.close(fig)
    figures.append(dict(stem=stem,taxels=list(range(start,start+3)),points=int(pool[pool.taxel.between(start,start+2)].frames.sum())))

summary={'date':'2026-10-19','source':str(SOURCE),'source_sha256':sha(SOURCE),'best_predictions_sha256':sha(PRED),
    'scope':{'frames':7154,'recordings':54,'taxels':9,'test_groups':6,'force_interval_N':[.05,3],
             'signal':'Original acquisition ROI mean HSV V from the pressed taxel; no floor correction or smoothing',
             'pairing':'Existing fold-specific lag-aligned reference_force_N; no new lag selection',
             'exclusions':'Replay-only, automatic, and dedicated no-contact recordings; all 7154 eligible press frames kept'},
    'method':{'weight':'Each frame has 1/n_s, so each of six press recordings has equal total weight within a taxel',
              'correlation':'Weighted Pearson correlation of force and raw ROI mean V, centered at weighted means',
              'fit':'V_hat = intercept + slope * reference force; weighted least squares with an intercept',
              'r2':'1 - weighted SSE / weighted total V variance; in-sample descriptive fit R2, equal to Pearson r squared',
              'within_recording':'Ordinary Pearson and OLS with intercept in each recording; within-recording weights are constant',
              'interpretation':'These descriptive fits use the plotted samples. They are not new held-out model metrics or prospective calibration validation.'},
    'pooled':pooled,'within_recording':recordings,'figures':figures,'checks':CHECKS,'check_count':len(CHECKS),
    'preserved_report_sha256':sha(history/PDF.name)}
(OUT/'v_force_analysis.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(pool.to_string(index=False));print('Independent calculation checks:',len(CHECKS))
