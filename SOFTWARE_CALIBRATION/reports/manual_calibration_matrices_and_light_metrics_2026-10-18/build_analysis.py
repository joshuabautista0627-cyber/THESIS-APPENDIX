"""Reproduce confusion matrices and optical diagnostics from local evidence.

Run prepare_light_data.py once to verify and extract the original manual CSVs.
No model fitting, model selection, threshold tuning, or prediction changes.
"""
from pathlib import Path
import hashlib
import json
import platform
import zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, accuracy_score, balanced_accuracy_score, f1_score, precision_score, recall_score

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DATA = OUT/'data'
FIG = OUT/'figures'
FIG.mkdir(exist_ok=True)
RUN = ROOT/'calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909'
CHECKS, FIGURES, MATRIX_SUMMARIES = [], [], {}
plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11, 'axes.titlesize':14,
    'axes.labelsize':12, 'svg.fonttype':'none', 'figure.facecolor':'white',
    'axes.spines.top':False, 'axes.spines.right':False})

def check(name, condition):
    assert condition, name
    CHECKS.append(name)

def safe(value):
    if isinstance(value, dict): return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)): return [safe(v) for v in value]
    if isinstance(value, np.ndarray): return safe(value.tolist())
    if isinstance(value, np.generic): return safe(value.item())
    if isinstance(value, float) and not np.isfinite(value): return None
    return value

def write_json(path, value):
    path.write_text(json.dumps(safe(value), indent=2, allow_nan=False), encoding='utf-8')

def save(fig, stem, caption):
    fig.savefig(FIG/(stem+'.png'), dpi=300, facecolor='white')
    fig.savefig(FIG/(stem+'.svg'), facecolor='white')
    plt.close(fig)
    FIGURES.append({'stem':stem, 'caption':caption})

def matrix(ax, values, labels, mode='percent', xlabel='Predicted class', ylabel='Actual class', vmin=0, vmax=None, cmap='Blues', support=None):
    if vmax is None: vmax = 100 if mode == 'percent' else values.max()
    im = ax.imshow(values, vmin=vmin, vmax=vmax, cmap=cmap, interpolation='nearest', aspect='equal')
    ax.set_xticks(range(len(labels)), labels)
    ax.set_yticks(range(values.shape[0]), labels if values.shape[0] == len(labels) else [f'TEST {g}' for g in range(1,7)])
    ax.set_xlabel(xlabel, labelpad=10); ax.set_ylabel(ylabel, labelpad=10)
    ax.set_xticks(np.arange(-.5,values.shape[1],1), minor=True)
    ax.set_yticks(np.arange(-.5,values.shape[0],1), minor=True)
    ax.grid(which='minor', color='white', linewidth=1.2)
    ax.tick_params(which='minor', bottom=False, left=False)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            v = values[i,j]
            label = f'{int(v):,}' if mode == 'count' else (f'{v:.2f}' if mode == 'correlation' else f'{v:.1f}')
            if support is not None: label += f'\nn={int(support[i,j]):,}'
            dark = abs(v) > .55 if mode == 'correlation' else v > .57*vmax
            ax.text(j,i,label,ha='center',va='center',fontsize=20 if len(labels)==2 else (9 if support is not None else 10), color='white' if dark else '#172D3D')
    return im

pred = pd.read_parquet(DATA/'held_out_predictions.parquet')
original = pd.read_parquet(RUN/'outer_predictions.parquet')
comparison = pd.read_csv(RUN/'model_comparison.csv')

def make_matrices(task, model='Tuned selected', key=None):
    if key is None: key=task
    d = original[(original.task == task)&(original.model == model)].copy()
    labels = list(range(1,10)) if task == 'localization' else [0,1]
    d['truth'] = d.truth.astype(int); d['prediction'] = d.prediction.astype(int)
    check(key+' unique IDs', not d.frame_uid.duplicated().any())
    check(key+' held-out groups', d.group.eq(d.outer_fold).all() and set(d.group)==set(range(1,7)))
    check(key+' complete recordings', d.groupby('session_id').outer_fold.nunique().eq(1).all())
    check(key+' manual roles', set(d.scientific_role) <= {'model_primary','no_contact'})
    weights = 1/d.groupby('session_id').session_id.transform('size')
    counts = confusion_matrix(d.truth,d.prediction,labels=labels)
    wp = confusion_matrix(d.truth,d.prediction,labels=labels,sample_weight=weights)
    percent = counts / counts.sum(axis=1,keepdims=True)*100
    weighted_percent = wp / wp.sum(axis=1,keepdims=True)*100
    check(key+' counts reconcile', counts.sum()==len(d))
    check(key+' normalized rows', np.allclose(percent.sum(axis=1),100) and np.allclose(weighted_percent.sum(axis=1),100))
    independent = pd.crosstab(d.truth,d.prediction).reindex(index=labels,columns=labels,fill_value=0).to_numpy()
    check(key+' independent raw counts', np.array_equal(counts,independent))
    record_recalls = []
    for label in labels:
        by_session = [np.bincount(s.prediction.to_numpy()-(1 if task=='localization' else 0), minlength=len(labels))/len(s)
                      for _,s in d[d.truth==label].groupby('session_id')]
        record_recalls.append(np.mean(by_session,axis=0)*100)
    check(key+' independent equal-recording percentages', np.allclose(weighted_percent,record_recalls))
    names = [f'T{i}' for i in labels] if task=='localization' else ['No contact','Contact']
    for suffix, a in [('raw_counts',counts),('row_normalized_percent',percent),('equal_recording_row_percent',weighted_percent)]:
        frame = pd.DataFrame(a,index=names,columns=names)
        frame.index.name='actual'; frame.columns.name='predicted'
        frame.to_csv(DATA/f'{key}_{suffix}.csv')
    metrics = {}
    for weight_name,w in [('frame_weighted',None),('equal_recording',weights)]:
        metrics[weight_name] = {'accuracy':accuracy_score(d.truth,d.prediction,sample_weight=w),
            'balanced_accuracy':balanced_accuracy_score(d.truth,d.prediction,sample_weight=w),
            'macro_f1':f1_score(d.truth,d.prediction,average='macro',sample_weight=w)}
        if task == 'contact':
            cm = counts if w is None else wp
            metrics[weight_name].update(precision=precision_score(d.truth,d.prediction,sample_weight=w),
                recall=recall_score(d.truth,d.prediction,sample_weight=w),
                contact_f1=f1_score(d.truth,d.prediction,sample_weight=w),
                specificity=cm[0,0]/cm[0].sum(), false_positive_rate=cm[0,1]/cm[0].sum())
    expected=comparison[(comparison.task==task)&(comparison.model==model)].iloc[0]
    check(key+' agrees with original report', all(np.isclose(metrics['equal_recording'][m],expected[m],atol=1e-12) for m in ['accuracy','balanced_accuracy','macro_f1']))
    MATRIX_SUMMARIES[key]={'model':model,'frames':len(d),'recordings':d.session_id.nunique(),'raw_counts':counts,'row_normalized_percent':percent,
                         'equal_recording_row_percent':weighted_percent,'metrics':metrics}
    return d,counts,percent,weighted_percent,names

loc = make_matrices('localization')
con = make_matrices('contact')
# CSV-only companion evaluations of the families used for final full-data fits.
make_matrices('localization','Tuned ensemble','supplement_localization_ensemble')
make_matrices('contact','Tuned RBF SVC','supplement_contact_svc')
check('Correct primary frame counts', len(loc[0])==7154 and len(con[0])==8506)
check('Contact and localization positive IDs agree', set(loc[0].frame_uid)==set(con[0][con[0].truth==1].frame_uid))

def confusion_figure(task, result, kind, stem):
    d,counts,pct,wp,labels = result
    a = {'raw':counts,'normalized':pct,'weighted':wp}[kind]
    title = ('Nine-taxel localization' if task=='localization' else 'Contact detection')+' confusion matrix'
    subtitle={'raw':'Raw counts — integer frames', 'normalized':'Row-normalized view — raw counts divided by each row total',
              'weighted':'Supplement — row-normalized after equal-recording weighting'}[kind]
    fig,ax=plt.subplots(figsize=(10.4,9.5) if task=='localization' else (9.8,8.8))
    fig.subplots_adjust(left=.14,right=.89,bottom=.19 if task=='localization' else .26,top=.81 if task=='localization' else .78)
    im=matrix(ax,a,labels,mode='count' if kind=='raw' else 'percent')
    fig.colorbar(im,ax=ax,fraction=.042,pad=.035,label='Frames' if kind=='raw' else 'Actual-class outcomes (%)')
    fig.suptitle(title,x=.08,y=.97,ha='left',fontsize=19,fontweight='bold')
    fig.text(.08,.925 if task=='localization' else .91,subtitle,fontsize=11)
    fig.text(.08,.885 if task=='localization' else .865,f'Tuned nested selector | Six held-out TEST groups | {len(d):,} frames | {d.session_id.nunique()} recordings',fontsize=10.5)
    support=', '.join(f'{name}: {n:,}' for name,n in zip(labels,counts.sum(axis=1)))
    if task=='localization':
        fig.text(.08,.115,'Actual-row frame totals: '+support[:support.index('T6:')].rstrip(', '),fontsize=9)
        fig.text(.08,.09,'                                     '+support[support.index('T6:'):],fontsize=9)
    else:
        fig.text(.08,.12,'Actual-row totals: '+support,fontsize=10)
        fig.text(.08,.087,'TN: upper left; FP: upper right; FN: lower left; TP: lower right.',fontsize=10)
    fig.text(.08,.054,'Manual data only; contact positives use aligned force 0.05–3 N. Retrospective evaluation.',fontsize=9.5)
    detail={'raw':'Cells are unweighted integer frame counts.',
            'normalized':'Each cell is 100 times the raw count divided by the total of its actual-class row. Every row sums to 100%.',
            'weighted':'Each frame has weight 1 divided by its recording frame count; actual-class rows are then normalized to 100%. These percentages intentionally differ from the raw-count ratios.'}[kind]
    save(fig,stem,f'{title}. Rows are actual labels; columns predicted labels. {detail} T1–T9 identify the nine taxels/ROIs. Saved predictions are from the six outer group-held-out folds of the tuned nested selection procedure, not from evaluating a full-data refit on training data. {len(d):,} frames in {d.session_id.nunique()} manual recordings; press interval 0.05–3 N, plus dedicated no-contact recordings for the contact task.')

confusion_figure('localization',loc,'normalized','01_localization_9x9_row_normalized')
confusion_figure('localization',loc,'raw','02_localization_9x9_raw_counts')
confusion_figure('contact',con,'normalized','03_contact_2x2_row_normalized')
confusion_figure('contact',con,'raw','04_contact_2x2_raw_counts')
confusion_figure('localization',loc,'weighted','05_supplement_localization_equal_recording')
confusion_figure('contact',con,'weighted','06_supplement_contact_equal_recording')

# Optical diagnostics use acquisition-time data with exact frame identity matching.
optical = pd.read_parquet(DATA/'matched_acquisition_optical_measurements.parquet')
check('Optical input contains exactly the evaluated contact rows',set(optical.frame_uid)==set(con[0].frame_uid))
press = optical[optical.scientific_role=='model_primary'].copy()
controls = optical[optical.scientific_role=='no_contact'].copy()
check('Manual light diagnostic cohort', len(press)==7154 and len(controls)==1352 and controls.session_id.nunique()==11)
check('Aligned force range', press.reference_force_N.between(.05,3).all())
columns = [f'roi{i}_delta_v_sum_per_pixel' for i in range(1,10)]
noise_records=[]
for sid,s in controls.groupby('session_id'):
    check(sid+' chronological no-contact timestamps', np.all(np.diff(s.elapsed_time_s)>0))
    q=max(1,len(s)//4)
    for i,col in enumerate(columns,1):
        x=s[col].to_numpy(float); raw=s[f'roi{i}_mean_v'].to_numpy(float)
        noise_records.append({'session_id':sid,'outer_fold':int(s.group.iloc[0]),'taxel':i,'frames':len(s),
            'mean_positive_delta_v':np.mean(x),'median_positive_delta_v':np.median(x),'sd_positive_delta_v':np.std(x,ddof=1),
            'robust_sigma_positive_delta_v':1.4826*np.median(np.abs(x-np.median(x))),
            'mean_raw_v':raw.mean(),'raw_v_last_minus_first_quartile':np.median(raw[-q:])-np.median(raw[:q]),
            'mean_active_fraction_percent':s[f'roi{i}_active_fraction'].mean()*100,
            'frames_with_max_v_255':int(s[f'roi{i}_max_v'].eq(255).sum())})
noise=pd.DataFrame(noise_records)
noise.to_csv(DATA/'light_no_contact_by_recording_taxel.csv',index=False)
fold_rows=[]
corrected=np.zeros((len(press),9))
sigmas=np.zeros((len(press),9))
for fold in range(1,7):
    training=controls[controls.group!=fold]
    held_ids=set(optical[optical.group==fold].session_id)
    check(f'Fold {fold} optical floor excludes held-out recordings',not set(training.session_id)&held_ids)
    floor=training.groupby('session_id')[columns].median().median(axis=0).to_numpy()
    noise_fit=noise[noise.outer_fold!=fold]
    sigma=np.sqrt(noise_fit.groupby('taxel').sd_positive_delta_v.apply(lambda v:np.mean(v*v))).to_numpy()
    check(f'Fold {fold} finite positive noise', np.isfinite(sigma).all() and (sigma>0).all())
    mask=press.group.to_numpy()==fold
    corrected[mask]=np.maximum(press.loc[mask,columns].to_numpy()-floor,0)
    sigmas[mask]=sigma
    for i in range(1,10):
        fold_rows.append({'outer_fold':fold,'taxel':i,'training_control_recordings':training.session_id.nunique(),
            'training_control_frames':len(training),'floor_delta_v':floor[i-1],'noise_sd_delta_v':sigma[i-1],
            'training_session_ids':'|'.join(sorted(training.session_id.unique()))})
pd.DataFrame(fold_rows).to_csv(DATA/'light_fold_reference_floors_and_noise.csv',index=False)
totals=corrected.sum(axis=1)
shares=np.divide(corrected,totals[:,None],out=np.full_like(corrected,np.nan),where=totals[:,None]>0)*100
target=press.target_roi.to_numpy(int)-1
raw=press[columns].to_numpy()
press['target_positive_delta_v']=raw[np.arange(len(press)),target]
press['target_excess_delta_v']=corrected[np.arange(len(press)),target]
press['target_active_fraction_percent']=np.array([row[f'roi{int(row.target_roi)}_active_fraction'] for _,row in press.iterrows()])*100
press['target_response_share_percent']=shares[np.arange(len(press)),target]
press['response_to_noise_ratio']=press.target_excess_delta_v/sigmas[np.arange(len(press)),target]
for i in range(1,10):
    press[f'share_T{i}_percent']=shares[:,i-1]
    press[f'excess_T{i}']=corrected[:,i-1]
session_rows=[]
share_cols=[f'share_T{i}_percent' for i in range(1,10)]
for sid,s in press.groupby('session_id'):
    i=int(s.target_roi.iloc[0])
    rho=s.reference_force_N.corr(s.target_positive_delta_v,method='spearman')
    mean_excess=s[[f'excess_T{j}' for j in range(1,10)]].mean().to_numpy()
    check(sid+' nonzero recording response denominator', mean_excess.sum()>0)
    recording_shares=100*mean_excess/mean_excess.sum()
    session_rows.append({'session_id':sid,'outer_fold':int(s.group.iloc[0]),'taxel':i,'frames':len(s),
        'min_force_N':s.reference_force_N.min(),'max_force_N':s.reference_force_N.max(),
        'mean_target_positive_delta_v':s.target_positive_delta_v.mean(),'mean_target_excess_delta_v':s.target_excess_delta_v.mean(),
        'mean_target_active_fraction_percent':s.target_active_fraction_percent.mean(),
        'mean_target_response_share_percent':recording_shares[i-1],
        'mean_response_to_noise_ratio':s.response_to_noise_ratio.mean(),'force_light_spearman_rho':rho,
        'zero_total_excess_frames':int(s[share_cols].isna().all(axis=1).sum()),
        'frames_with_target_max_v_255':int(s[f'roi{i}_max_v'].eq(255).sum()),
        **{col:recording_shares[j] for j,col in enumerate(share_cols)}})
sessions=pd.DataFrame(session_rows)
sessions.to_csv(DATA/'light_press_by_recording.csv',index=False)
check('All force correlations defined',np.isfinite(sessions.force_light_spearman_rho).all())
cross=sessions.groupby('taxel')[share_cols].mean()
check('Optical response share rows sum to 100 percent',np.allclose(cross.sum(axis=1),100))
cross.columns=[f'T{i}' for i in range(1,10)];cross.index=[f'T{i}' for i in range(1,10)]
cross.index.name='pressed_taxel';cross.columns.name='measured_taxel'
cross.to_csv(DATA/'light_response_distribution_percent.csv')
summary_rows=[]
for i in range(1,10):
    s=sessions[sessions.taxel==i];n=noise[noise.taxel==i]
    summary_rows.append({'taxel':i,'press_recordings':len(s),'press_frames':s.frames.sum(),'control_recordings':len(n),'control_frames':n.frames.sum(),
        'mean_target_positive_delta_v':s.mean_target_positive_delta_v.mean(),
        'mean_target_excess_delta_v':s.mean_target_excess_delta_v.mean(),
        'no_contact_mean_positive_delta_v':n.mean_positive_delta_v.mean(),
        'no_contact_rms_within_recording_sd_delta_v':np.sqrt(np.mean(n.sd_positive_delta_v**2)),
        'no_contact_median_robust_sigma_delta_v':n.robust_sigma_positive_delta_v.median(),
        'mean_active_area_percent':s.mean_target_active_fraction_percent.mean(),
        'mean_target_response_share_percent':s.mean_target_response_share_percent.mean(),
        'mean_off_target_response_share_percent':100-s.mean_target_response_share_percent.mean(),
        'mean_response_to_noise_ratio':s.mean_response_to_noise_ratio.mean(),
        'median_force_light_spearman_rho':s.force_light_spearman_rho.median(),
        'min_recording_force_light_rho':s.force_light_spearman_rho.min(),
        'max_recording_force_light_rho':s.force_light_spearman_rho.max(),
        'median_no_contact_raw_v_quartile_drift':n.raw_v_last_minus_first_quartile.median(),
        'target_max_v_255_frames':s.frames_with_target_max_v_255.sum(),
        'zero_total_excess_frames':s.zero_total_excess_frames.sum()})
summary=pd.DataFrame(summary_rows)
summary.to_csv(DATA/'light_metrics_by_taxel.csv',index=False)
press[['frame_uid','session_id','group','target_roi','reference_force_N','target_positive_delta_v','target_excess_delta_v',
       'target_active_fraction_percent','target_response_share_percent','response_to_noise_ratio']+share_cols].to_parquet(DATA/'light_diagnostic_frame_values.parquet',index=False)

fig,ax=plt.subplots(figsize=(10.4,9.5));fig.subplots_adjust(left=.14,right=.89,bottom=.22,top=.81)
im=matrix(ax,cross.to_numpy(),[f'T{i}' for i in range(1,10)],xlabel='Measured taxel',ylabel='Pressed taxel')
fig.colorbar(im,ax=ax,fraction=.042,pad=.035,label='Share of summed area-normalized response (%)')
fig.suptitle('Optical response distribution across nine taxels',x=.07,y=.97,ha='left',fontsize=18,fontweight='bold')
fig.text(.07,.925,'Spatial spread / cross-talk proxy from recorded optical measurements',fontsize=11)
fig.text(.07,.885,'7,154 press frames | Six recordings per pressed taxel | Reference floors exclude held-out groups',fontsize=10)
fig.text(.07,.12,'Per recording: average excess mean ΔV for each taxel, then normalize the nine values to 100%.',fontsize=10)
fig.text(.07,.085,'Each row averages six recording profiles. Values describe response spread, not prediction accuracy.',fontsize=10)
fig.text(.07,.05,f'All 7,154 frames retained, including {int((totals==0).sum()):,} zero-total frames. Camera units, not optical power.',fontsize=10)
save(fig,'07_light_response_distribution', 'Optical response-distribution matrix, distinct from a classifier confusion matrix. For each taxel, D is the ROI mean positive baseline-subtracted V. Its reference floor is the median of no-contact recording medians outside the corresponding held-out group. E=max(D-floor,0). For each recording, average E_j over all eligible frames, then divide each taxel mean by the sum of the nine means and multiply by 100. Average these normalized recording profiles equally across the six recordings of each pressed taxel. All 7,154 frames are retained, including 1,153 frames with zero total excess. Every recording has a nonzero mean-response denominator. Off-diagonal response is an exploratory cross-talk/spread proxy, not calibrated optical power leakage. Acquisition CSVs are joined exactly to the held-out frame IDs.')

fig,axes=plt.subplots(2,2,figsize=(12,9));fig.subplots_adjust(left=.09,right=.97,bottom=.14,top=.81,hspace=.48,wspace=.3)
panels=[('mean_target_excess_delta_v','Target response above reference floor','Mean positive ΔV (8-bit levels)'),
        ('no_contact_rms_within_recording_sd_delta_v','No-contact temporal noise','RMS within-recording SD (8-bit levels)'),
        ('mean_active_area_percent','Active area of the pressed taxel','Mean active pixels (%)'),
        ('mean_response_to_noise_ratio','Response-to-noise ratio (proxy)','Mean excess response / reference noise SD')]
for ax,(col,title,ylabel) in zip(axes.flat,panels):
    values=summary[col].to_numpy();ax.bar(range(1,10),values,color='#245F85',width=.68)
    ax.set_xticks(range(1,10),[f'T{i}' for i in range(1,10)]);ax.set_ylabel(ylabel,fontsize=10);ax.set_title(title,pad=12)
    ax.set_ylim(0,max(values)*1.22);ax.set_axisbelow(True);ax.grid(axis='y',color='#E2E7EA',linewidth=.6)
    for i,v in enumerate(values,1):ax.text(i,v+max(values)*.025,f'{v:.3f}' if 'sd_delta_v' in col else f'{v:.2f}',ha='center',fontsize=9)
fig.suptitle('Light-response metrics by taxel',x=.09,y=.97,ha='left',fontsize=20,fontweight='bold')
fig.text(.09,.92,'Manual acquisition CSVs | Equal recording weight | Positive frames restricted to 0.05–3 N',fontsize=11)
fig.text(.09,.875,'Press: 54 recordings / 7,154 frames. No contact: 11 recordings / 1,352 frames.',fontsize=11)
fig.text(.09,.075,'Active pixels: positive baseline-subtracted V ≥ 10. Noise uses temporal variation of each ROI mean.',fontsize=10)
fig.text(.09,.04,'The ratio uses reference noise fitted outside each held-out group; it is not a photometric or power SNR.',fontsize=10)
save(fig,'08_light_metrics_by_taxel','Four optical diagnostics from original manual acquisition CSVs: mean target excess positive ΔV after a fold-specific no-contact floor; RMS of within-recording temporal SD of mean positive ΔV in 11 no-contact recordings; pressed-taxel active area at the saved ΔV threshold of 10; and mean excess-response/reference-noise-SD ratio. Positive values are averaged within each press recording and then over six recordings per taxel. No-contact noise displayed uses all 11 control recordings descriptively, while each press ratio uses only control recordings outside its held-out group. These are camera-based diagnostics, not calibrated lux, mechanical sensitivity, or photometric SNR.')

corr=sessions.pivot(index='outer_fold',columns='taxel',values='force_light_spearman_rho')
corr.to_csv(DATA/'light_force_spearman_by_group_taxel.csv')
fig,ax=plt.subplots(figsize=(11,8.4));fig.subplots_adjust(left=.13,right=.91,bottom=.24,top=.78)
support=sessions.pivot(index='outer_fold',columns='taxel',values='frames').to_numpy()
im=matrix(ax,corr.to_numpy(),[f'T{i}' for i in range(1,10)],mode='correlation',xlabel='Pressed taxel',ylabel='Recording group',vmin=-1,vmax=1,cmap='PuOr_r',support=support)
fig.colorbar(im,ax=ax,fraction=.035,pad=.03,label='Spearman correlation (ρ)')
fig.suptitle('Association between force and target light response',x=.08,y=.96,ha='left',fontsize=18,fontweight='bold')
fig.text(.08,.90,'Per-recording Spearman correlation | Aligned reference force vs mean positive ΔV',fontsize=11)
fig.text(.08,.855,'54 manual press recordings | 7,154 eligible frames | Each cell shows ρ and its frame count n',fontsize=11)
fig.text(.08,.12,'Positive: larger light response tends to accompany larger force. Negative: the opposite tendency.',fontsize=10)
fig.text(.08,.083,'No extra lag was selected. Force targets retain the original fold-specific alignment.',fontsize=10)
fig.text(.08,.046,'Descriptive association only; temporal correlation and different force histories limit interpretation.',fontsize=10)
save(fig,'09_light_force_correlation','Spearman rank correlation between the target taxel mean positive ΔV recorded at acquisition and the lag-aligned reference force retained in the held-out prediction table. Each cell is one press recording in the 0.05–3 N interval. No new lag, signal threshold, or fitted regression was optimized. The fixed -1 to +1 color scale retains negative associations. These within-recording descriptive correlations are not independent-frame significance tests and do not establish linearity or causal sensitivity.')

metric_rows=[]
for procedure,entry in MATRIX_SUMMARIES.items():
    for weighting,metrics in entry['metrics'].items():
        metric_rows.append({'procedure':procedure,'weighting':weighting,'frames':entry['frames'],'recordings':entry['recordings'],**metrics})
pd.DataFrame(metric_rows).to_csv(DATA/'classification_metrics.csv',index=False)
write_json(OUT/'figure_manifest.json',FIGURES)
write_json(OUT/'metrics_and_validation.json',{'created_on':'2026-10-18','matrix_summaries':MATRIX_SUMMARIES,
    'optical_summary_by_taxel':summary.to_dict('records'),'checks':CHECKS,'visual_review':'pending',
    'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'matplotlib':matplotlib.__version__}})
(OUT/'Figure_Captions.txt').write_text('THESIS FIGURE CAPTIONS\n\n'+'\n\n'.join(f"{f['stem']}\n{f['caption']}" for f in FIGURES),encoding='utf-8')
print(json.dumps(safe({'checks_passed':len(CHECKS),'figures':len(FIGURES),'classification':MATRIX_SUMMARIES,
    'light_metrics':summary.to_dict('records')}),indent=2))
