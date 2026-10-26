"""Recording-level repeatability and force-adjusted blocked analysis.

No raw-data changes, no pass/fail threshold, no frame-level replication.
Run from any directory with the original analysis Python environment.
"""
from pathlib import Path
import hashlib, io, json, logging, os, platform, zipfile
import numpy as np
import pandas as pd
from scipy import stats, linalg
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parent/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs/repeatability_20261018'
SEED=20261018
B=50000
ROUNDS=['TEST1','TEST2','TEST3','TEST4','TEST5','TEST6','TEST7','TEST1_v2']
TAXELS=[f'T{i}' for i in range(1,10)]
FREF=3.5

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def save(df,name):
    df.to_csv(OUT/'tables'/f'{name}.csv',index=False)
    return df

def design(d,kind='main'):
    a=pd.get_dummies(d.taxel,drop_first=True,dtype=float)
    groups=d.trial_group
    if isinstance(groups.dtype,pd.CategoricalDtype):groups=groups.cat.remove_unused_categories()
    b=pd.get_dummies(groups,drop_first=True,dtype=float)
    arrays=[np.ones((len(d),1)),a.to_numpy(),b.to_numpy()]
    names=['Intercept']+[f'taxel:{c}' for c in a]+[f'round:{c}' for c in b]
    f=d.force_mean_N.to_numpy()-FREF
    if kind!='blocked_only':arrays.append(f[:,None]);names+=['force']
    if kind=='quadratic':arrays.append((f*f)[:,None]);names+=['force_squared']
    if kind=='duration':arrays.append(np.log(d.duration_s.to_numpy())[:,None]);names+=['log_duration']
    if kind=='taxel_slopes':arrays.append(a.to_numpy()*f[:,None]);names +=[f'force_x_{c}' for c in a]
    x=np.column_stack(arrays)
    assert np.linalg.matrix_rank(x)==x.shape[1]
    return x,names

def fit(d,kind='main',log=False):
    x,names=design(d,kind);y=d.optical_mean_delta_v.to_numpy()
    if log:y=np.log(y)
    b=np.linalg.lstsq(x,y,rcond=None)[0];res=y-x@b
    df=len(d)-x.shape[1];sse=float(res@res)
    h=np.sum(x*np.linalg.solve(x.T@x,x.T).T,axis=1)
    sigma=np.sqrt(sse/df)
    return dict(x=x,names=names,y=y,b=b,res=res,df=df,sse=sse,sigma=sigma,
                fitted=x@b,h=h,cook=(res/sigma)**2*h/(x.shape[1]*(1-h)**2))

def jackknife(d,group,kind='main',log=False):
    full=fit(d,kind,log);idx=full['names'].index('force');beta=full['b'][idx]
    values=[]
    for g in sorted(d[group].unique()):
        f=fit(d.loc[d[group].ne(g)],kind,log)
        values.append(dict(deleted=g,force_coefficient=float(f['b'][f['names'].index('force')]),residual_sd=float(f['sigma'])))
    v=np.array([r['force_coefficient'] for r in values]);G=len(v)
    se=np.sqrt((G-1)/G*np.sum((v-v.mean())**2));crit=stats.t.ppf(.975,G-1)
    return dict(estimate=float(beta),se=float(se),lower=float(beta-crit*se),upper=float(beta+crit*se),clusters=G,df=G-1,method='delete-one-cluster CV3J with t(G-1)'),pd.DataFrame(values)

def main():
    for sub in ['tables','figures']:(OUT/sub).mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',handlers=[logging.FileHandler(OUT/'analysis.log',mode='w'),logging.StreamHandler()])
    old=json.loads((ROOT/'outputs/summary.json').read_text())
    archive=Path(old['archive']);source_hash=digest(archive)
    assert source_hash==old['archive_sha256']
    r=pd.read_csv(ROOT/'outputs/tables/recording_summary.csv')
    d=r.loc[~r.no_contact_recording].copy()
    assert len(d)==72 and set(d.trial_group)==set(ROUNDS)
    assert pd.crosstab(d.trial_group,d.taxel).eq(1).all().all()
    assert d.session_id.nunique()==1 and d.session_id.iloc[0]=='S3'
    assert d.recording_id.is_unique
    errors=[]
    with zipfile.ZipFile(archive) as z:
        for _,row in d.iterrows():
            raw=pd.read_csv(z.open(row.archive_prefix+'/master_synchronized.csv'))
            good=raw.frame_valid & raw.baseline_valid & raw.loadcell_valid & raw.synchronization_valid
            sel=good & (raw.force_N>=raw.contact_threshold_N)
            for col,value in [('force_mean_N',raw.loc[sel,'force_N'].mean()),('optical_mean_delta_v',raw.loc[sel,f'roi{row.taxel[1:]}_delta_v_mean'].mean())]:
                errors.append(abs(row[col]-value))
            assert int(sel.sum())==row.contact_frames
    assert max(errors)<1e-10
    logging.info('Verified %d recording means from original archive; max error %.3g',len(errors),max(errors))
    d['trial_group']=pd.Categorical(d.trial_group,categories=ROUNDS,ordered=True)
    d=d.sort_values(['trial_group','taxel']).reset_index(drop=True)
    save(d,'analysis_recordings')
    Y=d.pivot(index='trial_group',columns='taxel',values='optical_mean_delta_v').reindex(index=ROUNDS,columns=TAXELS).to_numpy()
    F=d.pivot(index='trial_group',columns='taxel',values='force_mean_N').reindex(index=ROUNDS,columns=TAXELS).to_numpy()

    # One index represents a whole collection round with all nine taxels.
    # scipy computes BCa using delete-one-round acceleration and shared draws.
    def metrics(indices,axis=-1):
        ids=np.moveaxis(np.asarray(indices,dtype=int),axis,-1)
        y=Y[ids];f=F[ids];G=y.shape[-2];J=y.shape[-1]
        my=y.mean(axis=-2);sy=y.std(axis=-2,ddof=1)
        mf=f.mean(axis=-2);sf=f.std(axis=-2,ddof=1)
        raw=np.stack([my,sy,100*sy/my,mf,sf,100*sf/mf],axis=-2)
        raw=raw.reshape(raw.shape[:-2]+(54,))
        yd=y-y.mean(-2,keepdims=True)-y.mean(-1,keepdims=True)+y.mean((-2,-1),keepdims=True)
        fd=f-f.mean(-2,keepdims=True)-f.mean(-1,keepdims=True)+f.mean((-2,-1),keepdims=True)
        denom=np.sum(fd*fd,axis=(-2,-1))
        beta=np.sum(fd*yd,axis=(-2,-1))/denom
        er=yd-beta[...,None,None]*fd
        sse=np.sum(er*er,axis=(-2,-1));block=np.sum(yd*yd,axis=(-2,-1))
        taxel=np.sum((y-y.mean(-2,keepdims=True))**2,axis=(-2,-1))
        total=np.sum((y-y.mean((-2,-1),keepdims=True))**2,axis=(-2,-1))
        extra=np.stack([beta,np.sqrt(taxel/(J*(G-1))),np.sqrt(block/((J-1)*(G-1))),np.sqrt(sse/(J*G-J-G)),1-sse/total,1-sse/block],axis=-1)
        return np.moveaxis(np.concatenate([raw,extra],axis=-1),-1,0)

    point=metrics(np.arange(8))
    boot=stats.bootstrap((np.arange(8),),metrics,vectorized=True,axis=0,
        n_resamples=B,batch=1000,method='BCa',confidence_level=.95,rng=np.random.default_rng(SEED))
    assert np.isfinite(boot.bootstrap_distribution).all()
    low=np.asarray(boot.confidence_interval.low);high=np.asarray(boot.confidence_interval.high)
    assert np.isfinite(low).all() and np.isfinite(high).all()
    rawrows=[]
    for k,label in enumerate(['optical_mean','optical_sd','optical_cv_percent','force_mean','force_sd','force_cv_percent']):
        for j,taxel in enumerate(TAXELS):
            q=k*9+j
            rawrows.append(dict(taxel=taxel,statistic=label,estimate=point[q],ci95_lower=low[q],ci95_upper=high[q],n_recordings=8,interval='whole-round BCa bootstrap; 50000 resamples'))
    rawtable=save(pd.DataFrame(rawrows),'repeatability_intervals')
    modelnames=['force_coefficient','pooled_within_taxel_sd','taxel_round_residual_sd','force_adjusted_residual_sd','in_sample_r_squared','partial_r_squared_force_given_taxel_round']
    modeltable=save(pd.DataFrame([dict(statistic=name,estimate=point[54+k],ci95_lower=low[54+k],ci95_upper=high[54+k],interval='whole-round BCa bootstrap') for k,name in enumerate(modelnames)]),'model_bootstrap_intervals')
    base=fit(d,'blocked_only');full=fit(d)
    assert full['df']==55 and np.isclose(point[54],full['b'][-1],atol=1e-12)
    assert np.isclose(point[57],full['sigma'],atol=1e-12)
    # QR solution is a separate numerical cross-check of all OLS coefficients.
    q,rr=np.linalg.qr(full['x'],mode='reduced');bqr=linalg.solve_triangular(rr,q.T@full['y'])
    assert np.max(np.abs(bqr-full['b']))<1e-10
    primary,jr=jackknife(d,'trial_group');sensitivity,jt=jackknife(d,'taxel')
    save(jr,'delete_one_round');save(jt,'delete_one_taxel')
    save(pd.DataFrame([{'cluster_dimension':'round',**primary},{'cluster_dimension':'taxel',**sensitivity}]),'force_coefficient_uncertainty')
    pred=d[['recording_id','trial_group','taxel','force_mean_N','optical_mean_delta_v','duration_s']].copy()
    pred['fitted_optical']=full['fitted'];pred['residual']=full['res'];pred['leverage']=full['h'];pred['cooks_distance']=full['cook']
    pred['standardized_residual']=full['res']/(full['sigma']*np.sqrt(1-full['h']))
    save(pred,'model_residuals')
    force_ranges=save(d.groupby('taxel',observed=True).force_mean_N.agg(['min','max']).reset_index(),'force_ranges')
    overlap=[float(force_ranges['min'].max()),float(force_ranges['max'].min())]
    assert overlap[0]<FREF<overlap[1]
    roundmeans=Y.mean(1)-primary['estimate']*(F.mean(1)-FREF)
    effects=roundmeans-roundmeans.mean()
    rounds=save(pd.DataFrame(dict(trial_group=ROUNDS,n_recordings=9,raw_optical_mean=Y.mean(1),mean_force_N=F.mean(1),adjusted_round_deviation=effects)),'round_summaries')
    # Model sensitivity is disclosed rather than used to select a favorable result.
    specs=[]
    for kind,log,label in [('main',False,'Common linear force slope'),('main',True,'Log optical response'),('quadratic',False,'Quadratic force term'),('duration',False,'Log duration added'),('taxel_slopes',False,'Separate taxel force slopes')]:
        f=fit(d,kind,log);j,_=jackknife(d,'trial_group',kind,log)
        specs.append(dict(model=label,residual_df=f['df'],residual_sd=f['sigma'],response_scale='log delta V' if log else 'delta V',force_effect=j['estimate'],ci95_lower=j['lower'],ci95_upper=j['upper'],note='T1 slope only; interactions modify other taxels' if kind=='taxel_slopes' else 'Derivative at 3.5 N' if kind=='quadratic' else 'Common slope'))
    specs=save(pd.DataFrame(specs),'model_sensitivity')
    hetero=save(pred.groupby('taxel',observed=True).agg(n=('residual','size'),rms_residual=('residual',lambda s:np.sqrt(np.mean(s*s))),mean_abs_residual=('residual',lambda s:np.mean(np.abs(s)))).reset_index(),'residual_dispersion_by_taxel')
    split=d.groupby('trial_group',observed=True).agg(start=('start_utc','min'),end=('end_utc','max'),min_duration_s=('duration_s','min'),max_duration_s=('duration_s','max'),baseline_ids=('baseline_id','nunique')).reset_index()
    save(split,'round_acquisition_context')
    save(pd.crosstab(d.trial_group,d.baseline_id).reset_index(),'round_baseline_crosswalk')
    # Comparing first and last halves of deterministic draws quantifies Monte Carlo variation.
    cv_draws=boot.bootstrap_distribution[18:27]
    mc=float(np.max(np.abs(np.quantile(cv_draws[:,:B//2],[.025,.975],axis=1)-np.quantile(cv_draws[:,B//2:],[.025,.975],axis=1))))
    summary=dict(date='2026-10-18',archive=str(archive),archive_sha256=source_hash,recording_summary_sha256=digest(ROOT/'outputs/tables/recording_summary.csv'),
        n_recordings=72,n_taxels=9,n_rounds=8,source_session='S3',physical_press_count='unknown',acceptance_limit=None,
        seed=SEED,resamples=B,interval_level=.95,bootstrap='BCa; paired whole rounds with all nine taxels; no frame resampling',
        force_reference_N=FREF,common_force_range_N=overlap,force_effect_round_jackknife=primary,force_effect_taxel_jackknife=sensitivity,
        model_rank=full['x'].shape[1],residual_df=full['df'],sse=full['sse'],blocked_sse=base['sse'],residual_sd=full['sigma'],
        residual_sd_BCa=[float(low[57]),float(high[57])],pooled_within_taxel_sd=float(point[55]),pooled_sd_BCa=[float(low[55]),float(high[55])],
        blocked_residual_sd=base['sigma'],r_squared=float(point[58]),partial_r_squared_force=float(point[59]),
        adjusted_round_deviation_range=[float(effects.min()),float(effects.max())],max_cooks_distance=float(full['cook'].max()),
        max_leverage=float(full['h'].max()),residual_rms_taxel_range=[float(hetero.rms_residual.min()),float(hetero.rms_residual.max())],
        normal_qq_correlation=float(stats.probplot(full['res'])[1][2]),
        mean_source_verification_cells=len(errors),max_source_mean_difference=float(max(errors)),qr_coefficient_max_difference=float(np.max(np.abs(bqr-full['b']))),
        cv_percentile_endpoint_MC_half_difference_pp=mc,
        limitations=['Eight rounds only; BCa and t intervals are approximate, conditional on exchangeable/independent rounds.',
        'Same session and repeated physical taxels may induce dependence across rounds; taxel-jackknife sensitivity is not simultaneous two-way clustering.',
        'Round labels are matched condition groups, not always contiguous temporal blocks; baseline and acquisition order are partly confounded.',
        'One recording per taxel-round cell; taxel-by-round interaction and residual variation cannot be separated.',
        'Variable force and motion-magnified signals prevent intrinsic fixed-force sensor repeatability claims.',
        'No acceptance limit, equivalence test, pass/fail decision, or trained-model evaluation.'],
        software={'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':__import__('scipy').__version__,'matplotlib':matplotlib.__version__})
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    plots(rawtable,pred,rounds,primary,summary)
    logging.info('Completed source verification, BCa bootstrap and cluster-jackknife model. No records excluded.')
    print(json.dumps(summary,indent=2))

def plots(raw,pred,rounds,primary,summary):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':13,'axes.titlesize':15,'axes.labelcolor':'#273846','text.color':'#273846','axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'axes.axisbelow':True})
    def export(fig,name):
        fig.savefig(OUT/'figures'/f'{name}.png',dpi=320,bbox_inches='tight');fig.savefig(OUT/'figures'/f'{name}.svg',bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11.2,5.4))
    for ax,key,label,c in [(axes[0],'optical_cv_percent','Optical recording means','#245c86'),(axes[1],'force_cv_percent','Force recording means','#b48328')]:
        t=raw[raw.statistic.eq(key)].set_index('taxel').reindex(TAXELS);yy=np.arange(9)
        ax.hlines(yy,t.ci95_lower,t.ci95_upper,color=c,lw=2);ax.scatter(t.estimate,yy,color=c,s=35,zorder=3)
        ax.set(yticks=yy,yticklabels=TAXELS,xlabel='CV (%)',title=label,xlim=(0,None));ax.invert_yaxis()
    fig.suptitle('Observed variability with approximate 95% BCa intervals');fig.text(.5,.015,'Eight recordings per taxel; 50,000 whole-group resamples. No acceptance threshold.',ha='center',fontsize=11);fig.tight_layout(rect=(0,.045,1,.95));export(fig,'16_repeatability_uncertainty')
    fig,axes=plt.subplots(1,2,figsize=(11.2,5))
    y=pred.optical_mean_delta_v.to_numpy().reshape(8,9);f=pred.force_mean_N.to_numpy().reshape(8,9)
    yd=y-y.mean(0)-y.mean(1)[:,None]+y.mean();fd=f-f.mean(0)-f.mean(1)[:,None]+f.mean()
    axes[0].scatter(fd.ravel(),yd.ravel(),s=25,color='#245c86',alpha=.8)
    x=np.linspace(fd.min(),fd.max(),100);axes[0].plot(x,primary['estimate']*x,color='#a24e3e')
    axes[0].set(xlabel='Adjusted force (N)',ylabel='Adjusted optical response (digital delta V)',title='Conditional force association')
    axes[1].scatter(pred.fitted_optical,pred.residual,s=25,color='#245c86');axes[1].axhline(0,color='#a24e3e',lw=1)
    axes[1].set(xlabel='Fitted optical response (delta V)',ylabel='Residual optical response (delta V)',title='Residuals versus fitted response')
    fig.tight_layout();export(fig,'17_force_adjusted_diagnostics')
    fig,axes=plt.subplots(1,2,figsize=(11.2,5))
    axes[0].bar(rounds.trial_group,rounds.adjusted_round_deviation,color='#245c86');axes[0].axhline(0,color='#53616b',lw=1)
    axes[0].set(ylabel='Adjusted group offset (digital delta V)',title='Descriptive group offsets');axes[0].tick_params(axis='x',rotation=45)
    stats.probplot(pred.residual,plot=axes[1]);axes[1].get_lines()[0].set(color='#245c86',marker='o',markersize=4);axes[1].get_lines()[1].set(color='#a24e3e')
    axes[1].set(title='Residual normal Q-Q diagnostic',ylabel='Residual optical response (delta V)')
    fig.tight_layout();export(fig,'18_round_effects_residual_shape')
    jr=pd.read_csv(OUT/'tables/delete_one_round.csv');jt=pd.read_csv(OUT/'tables/delete_one_taxel.csv')
    fig,axes=plt.subplots(1,2,figsize=(11.2,4.6))
    for ax,t,title in [(axes[0],jr,'Omit one round'),(axes[1],jt,'Omit one taxel')]:
        ax.scatter(t.force_coefficient,t.deleted,color='#245c86');ax.axvline(primary['estimate'],color='#a24e3e',ls='--',label='Full-data estimate');ax.set(title=title,xlabel='Refitted force slope (delta V / N)');ax.legend(frameon=False,fontsize=11)
    fig.tight_layout();export(fig,'19_model_influence')

if __name__=='__main__':main()
