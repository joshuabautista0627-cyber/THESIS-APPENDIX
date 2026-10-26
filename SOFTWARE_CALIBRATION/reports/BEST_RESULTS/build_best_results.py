"""Consolidate the best manual-only evaluated model for each task.

Classification: maximize the established equal-recording accuracy.
Force: minimize equal-recording MAE. Never mix metrics between models.
This script writes only to its own BEST_RESULTS directory.
"""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from sklearn.metrics import confusion_matrix, accuracy_score, balanced_accuracy_score, f1_score, precision_score, recall_score, mean_absolute_error, mean_squared_error, r2_score

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
RUN=ROOT/'calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909'
BASE=RUN.parent/'retraining_20260909'
LIGHT=OUT.parent/'manual_calibration_matrices_and_light_metrics_2026-10-18'
DATA=OUT/'data';FIG=OUT/'figures';REF=OUT/'reference'
for folder in (DATA,FIG,REF):folder.mkdir(exist_ok=True)
CHECKS=[];FIGURES=[]
def check(name,ok):
    assert ok,name
    CHECKS.append(name)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def safe(v):
    if isinstance(v,dict):return {str(k):safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [safe(x) for x in v]
    if isinstance(v,np.ndarray):return safe(v.tolist())
    if isinstance(v,np.generic):return safe(v.item())
    if isinstance(v,float) and not np.isfinite(v):return None
    return v
def write_json(path,value):path.write_text(json.dumps(safe(value),indent=2,allow_nan=False),encoding='utf-8')

# Preserve every existing report file byte-for-byte, including competing versions.
prior={str(p.relative_to(ROOT)):sha(p) for folder in OUT.parent.iterdir() if folder.is_dir() and folder!=OUT
       for p in folder.rglob('*') if p.is_file()}
write_json(REF/'preserved_report_file_hashes.json',prior)
all_rows=pd.concat([pd.read_csv(BASE/'model_comparison.csv').assign(experiment='retraining_20260909'),
                    pd.read_csv(RUN/'model_comparison.csv').assign(experiment='tuning_20260909')],ignore_index=True)
winners={}
ranked=[]
for task in ['localization','contact','force']:
    objective='mae_N' if task=='force' else 'accuracy'
    ranking=all_rows[all_rows.task==task].sort_values(objective,ascending=task=='force').copy()
    ranking['rank_by_primary_metric']=range(1,len(ranking)+1)
    winners[task]=ranking.iloc[0]
    ranked.append(ranking)
pd.concat(ranked,ignore_index=True).to_csv(REF/'all_competing_models_ranked.csv',index=False)
check('Highest localization accuracy model',winners['localization'].model=='Tuned Logistic regression')
check('Highest contact accuracy model',winners['contact'].model=='Tuned RBF SVC')
check('Lowest force MAE model',winners['force'].model=='Tuned ensemble')
check('All winners come from the verified tuning run',all(r.experiment=='tuning_20260909' for r in winners.values()))
source=RUN/'outer_predictions.parquet'
check('Saved prediction source unchanged',sha(source)=='fda648280f60ca250e10a2e34e546a1677ae0a7cf0e7a6261c1bb9a3982e1817')
pred=pd.read_parquet(source)
rows={};metrics={};matrices={}
for task,winner in winners.items():
    d=pred[(pred.task==task)&(pred.model==winner.model)].copy()
    d['weight']=1/d.groupby('session_id').session_id.transform('size')
    check(task+' held-out groups',d.group.eq(d.outer_fold).all() and set(d.group)==set(range(1,7)))
    check(task+' whole recordings',d.groupby('session_id').outer_fold.nunique().eq(1).all())
    check(task+' unique frame IDs',not d.frame_uid.duplicated().any())
    check(task+' evaluated population',len(d)==int(winner.frames) and d.session_id.nunique()==int(winner.sessions))
    check(task+' manual roles',set(d.scientific_role)<={'model_primary','no_contact'})
    y,p,w=d.truth,d.prediction,d.weight
    if task=='force':
        score={'mae_N':mean_absolute_error(y,p,sample_weight=w),'rmse_N':np.sqrt(mean_squared_error(y,p,sample_weight=w)),
               'bias_N':np.average(p-y,weights=w),'r2':r2_score(y,p,sample_weight=w)}
        check('Force range',y.between(.05,3).all())
    else:
        d['truth']=y.astype(int);d['prediction']=p.astype(int)
        score={'accuracy':accuracy_score(y,p,sample_weight=w),'balanced_accuracy':balanced_accuracy_score(y,p,sample_weight=w),
               'macro_f1':f1_score(y,p,average='macro',sample_weight=w)}
        labels=list(range(1,10)) if task=='localization' else [0,1]
        counts=confusion_matrix(y,p,labels=labels)
        weighted=confusion_matrix(y,p,labels=labels,sample_weight=w)
        percent=weighted/weighted.sum(axis=1,keepdims=True)*100
        check(task+' raw count reconstruction',np.array_equal(counts,pd.crosstab(y,p).reindex(index=labels,columns=labels,fill_value=0).to_numpy()))
        independent=np.zeros_like(weighted)
        for _,s in d.groupby('session_id'):
            for a,b in zip(s.truth,s.prediction):independent[labels.index(a),labels.index(b)]+=1/len(s)
        check(task+' weighted count reconstruction',np.allclose(independent,weighted))
        check(task+' row sums and total counts',np.allclose(percent.sum(axis=1),100) and counts.sum()==len(d))
        names=[f'T{i}' for i in labels] if task=='localization' else ['No contact','Contact']
        for suffix,a in [('raw_counts',counts),('recording_weighted_counts',weighted),('row_normalized_percent',percent)]:
            df=pd.DataFrame(a,index=names,columns=names);df.index.name='actual';df.to_csv(DATA/f'{task}_{suffix}.csv')
        matrices[task]={'raw_counts':counts,'row_percent':percent,'labels':names}
        if task=='contact':
            score.update(precision=precision_score(y,p,sample_weight=w),recall=recall_score(y,p,sample_weight=w),
                         fpr=weighted[0,1]/weighted[0].sum(),specificity=weighted[0,0]/weighted[0].sum(),
                         contact_f1=f1_score(y,p,sample_weight=w))
    for metric,value in score.items():
        if metric in winner.index and pd.notna(winner[metric]):check(task+' audited '+metric,np.isclose(value,winner[metric],atol=1e-12))
    rows[task]=d
    metrics[task]={'model':winner.model,'frames':len(d),'recordings':d.session_id.nunique(),**score}
check('Same press frame identities for all tasks',set(rows['force'].frame_uid)==set(rows['localization'].frame_uid)==set(rows['contact'][rows['contact'].truth==1].frame_uid))
pd.concat(rows.values(),ignore_index=True).to_parquet(DATA/'best_models_held_out_predictions.parquet',index=False)
pd.DataFrame([{'task':t,**m} for t,m in metrics.items()]).to_csv(OUT/'BEST_METRICS.csv',index=False)
write_json(OUT/'BEST_METRICS.json',{'weighting':'Equal total weight per recording for every reported metric','selection':'Highest classification accuracy; lowest force MAE among evaluated manual-only models','results':metrics})

# Exactly the configurations that generated the winning families' held-out predictions.
protocol=json.loads((RUN/'protocol.json').read_text())
candidate={c['id']:c for c in protocol['candidates']}
dimensions={'positive':9,'optical':27,'shape':90,'spatial':180,'invariant':117,'temporal':288}
def configuration(choice):
    keep={k:choice[k] for k in ['id','family','tau','h','threshold','threshold_policy','offset','correction'] if k in choice}
    if 'members' in choice:
        keep['combination']='Unweighted arithmetic mean of member predictions after their selected causal EMA and corrections'
        keep['members']=[configuration(m) for m in choice['members']]
    else:
        c=candidate[choice['id']];keep['candidate']=c
        params=dict(c['params']);family=c['family']
        defaults={'Logistic regression':dict(max_iter=2500,random_state=1741),
          'RBF SVC':dict(cache_size=256,decision_function_shape='ovr',random_state=1741),
          'Extra Trees':dict(n_estimators=180,n_jobs=1,random_state=1741),
          'HistGB':dict(max_iter=180,learning_rate=.05,min_samples_leaf=20,early_stopping=False,random_state=1741),
          'XGBoost':dict(n_estimators=220,learning_rate=.04,min_child_weight=5,tree_method='hist',n_jobs=1,random_state=1741)}
        if family=='RBF SVC':params['gamma']=params.pop('gamma_multiplier')/dimensions[c['features']]
        keep['explicit_estimator_parameters']={**defaults[family],**params}
        keep['feature_count']=dimensions[c['features']]
    return keep
fold_configs={}
for fold in range(1,7):
    choices=json.loads((RUN/f'selections_fold{fold}.json').read_text())
    fold_configs[str(fold)]={task:configuration(choices[task][winner.model]) for task,winner in winners.items()}
exact=json.loads((OUT.parent/'manual_calibration_thesis_report_2026-10-05/Exact_Segmentation_and_Model_Configurations.json').read_text())
write_json(OUT/'BEST_MODEL_CONFIGURATIONS.json',{'scope':'Configurations of the six held-out fold models used for the reported winning family metrics',
    'metric_source':'Saved outer-fold predictions; inner-selection scores are deliberately not reported as test metrics',
    'roi_layout':exact['roi_layout'],'segmentation':{'positive_pixel_delta':'max(V_current - V_baseline, 0), evaluated per pixel',
    'active_delta_v_threshold':10.0,'active_fraction':'Active pixel count / ROI area','morphology':'none'},
    'fold_model_configurations':fold_configs,'training_scale':'StandardScaler fitted with training weights only',
    'history':'Causal EMA; reset at recording boundary, nonpositive dt, or gap greater than 0.3 s',
    'selection_criterion_for_this_report':{'classification':'Highest equal-recording accuracy','force':'Lowest equal-recording MAE'}})

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':15,'axes.labelsize':12,
    'svg.fonttype':'none','figure.facecolor':'white','axes.spines.top':False,'axes.spines.right':False})
def save(fig,stem,caption):
    fig.savefig(FIG/f'{stem}.png',dpi=300);fig.savefig(FIG/f'{stem}.svg');plt.close(fig)
    FIGURES.append({'stem':stem,'caption':caption})
def draw_matrix(task,raw,stem):
    m=matrices[task];values=m['raw_counts'] if raw else m['row_percent'];labels=m['labels']
    n=len(labels);fig,ax=plt.subplots(figsize=(10.5,9.6) if n==9 else (9.8,8.8))
    fig.subplots_adjust(left=.14,right=.89,bottom=.23,top=.78)
    vmax=values.max() if raw else 100
    im=ax.imshow(values,vmin=0,vmax=vmax,cmap='Blues',interpolation='nearest')
    ax.set_xticks(range(n),labels);ax.set_yticks(range(n),labels)
    ax.set_xlabel('Predicted taxel' if n==9 else 'Predicted status',labelpad=12)
    ax.set_ylabel('Actual taxel' if n==9 else 'Actual status',labelpad=12)
    ax.set_xticks(np.arange(-.5,n,1),minor=True);ax.set_yticks(np.arange(-.5,n,1),minor=True)
    ax.grid(which='minor',color='white',linewidth=1.3);ax.tick_params(which='minor',bottom=False,left=False)
    for y in range(n):
        for x in range(n):
            v=values[y,x];text=f'{int(v):,}' if raw else f'{v:.1f}'
            ax.text(x,y,text,ha='center',va='center',fontsize=10 if n==9 else 22,color='white' if v>.57*vmax else '#142D3D')
    fig.colorbar(im,ax=ax,fraction=.042,pad=.035,label='Frames' if raw else 'Actual-class outcomes (%)')
    name='Localization' if n==9 else 'Contact detection'
    family='Tuned Logistic Regression' if n==9 else 'Tuned RBF SVC'
    fig.suptitle(f'{name} — best accuracy model',x=.08,y=.97,ha='left',fontsize=20,fontweight='bold')
    fig.text(.08,.91,f'{family} | Accuracy {metrics[task]["accuracy"]:.2%}',fontsize=13)
    fig.text(.08,.86,f'Six held-out TEST groups | {metrics[task]["frames"]:,} frames | {metrics[task]["recordings"]} recordings',fontsize=11)
    fig.text(.08,.14,'RAW COUNTS — unweighted integer frames' if raw else 'ROW-NORMALIZED (%) — each recording has equal total weight',fontsize=11,fontweight='bold')
    fig.text(.08,.095,'Manual calibration only | Positive force range: 0.05–3 N',fontsize=10)
    fig.text(.08,.055,'Accuracy uses equal recording weights; raw counts separately show every evaluated frame.',fontsize=10)
    save(fig,stem,f'{name} confusion matrix for {family}, the evaluated model with the highest equal-recording accuracy. Rows are actual classes and columns predicted classes. '+
        ('Cells are unweighted integer frame counts.' if raw else 'Each frame has weight 1 divided by the evaluated frames in its recording; each actual-class row is then normalized to 100%.')+
        f' Six complete TEST groups were held out, covering {metrics[task]["frames"]:,} frames and {metrics[task]["recordings"]} manual recordings. Model-family ranking is retrospective; these are held-out fold predictions.')
draw_matrix('localization',False,'01_best_localization_9x9_normalized')
draw_matrix('localization',True,'02_best_localization_9x9_raw_counts')
draw_matrix('contact',False,'03_best_contact_2x2_normalized')
draw_matrix('contact',True,'04_best_contact_2x2_raw_counts')

roi=[]
for i in range(1,10):
    l=rows['localization'][rows['localization'].truth==i]
    c=rows['contact'][(rows['contact'].truth==1)&(rows['contact'].target_roi==i)]
    roi.append({'taxel':i,'frames':len(l),'localization_recall_percent':100*l.assign(correct=l.truth.eq(l.prediction)).groupby('session_id').correct.mean().mean(),
                'contact_recall_percent':100*c.groupby('session_id').prediction.mean().mean()})
roi=pd.DataFrame(roi);roi.to_csv(DATA/'best_models_per_taxel.csv',index=False)
fig,axes=plt.subplots(1,2,figsize=(12,8.6));fig.subplots_adjust(left=.08,right=.88,top=.80,bottom=.16,wspace=.28)
cmap=plt.get_cmap('Blues');norm=plt.Normalize(0,100)
for ax,col,title in zip(axes,['localization_recall_percent','contact_recall_percent'],['Logistic Regression: localization','RBF SVC: contact detection']):
    ax.set_title(title,fontsize=13,pad=15);ax.set_xlim(70,400);ax.set_ylim(480,130);ax.set_aspect('equal')
    ax.set_xlabel('Image x (pixels)');ax.set_ylabel('Image y (pixels)')
    for rect in exact['roi_layout']['rois']:
        i=rect['roi_id'];v=roi.set_index('taxel').loc[i,col]
        ax.add_patch(Rectangle((rect['x'],rect['y']),rect['width'],rect['height'],facecolor=cmap(norm(v)),edgecolor='#284858'))
        ax.text(rect['center_x'],rect['center_y'],f'T{i}\n{v:.1f}%',ha='center',va='center',color='white' if v>57 else '#142D3D',fontsize=11)
cax=fig.add_axes([.92,.24,.018,.45]);fig.colorbar(plt.cm.ScalarMappable(cmap=cmap,norm=norm),cax=cax,label='Recall (%)')
fig.suptitle('Best-model performance across the nine taxels',x=.08,y=.97,ha='left',fontsize=20,fontweight='bold')
fig.text(.08,.91,'Held-out manual recordings | Six press recordings per taxel | Equal recording weights',fontsize=11)
fig.text(.08,.09,'Localization: correct taxel. Contact detection: contact found during a positive press.',fontsize=10)
fig.text(.08,.045,'Rectangles use the saved image ROI geometry. Colors represent recall, not light intensity.',fontsize=10)
save(fig,'05_best_models_taxel_heatmaps','Held-out localization recall for tuned Logistic Regression and positive-contact recall for tuned RBF SVC, mapped to the saved nine taxel ROI rectangles in oriented camera pixel coordinates. Each taxel value averages six recording recalls. No-contact specificity is evaluated separately in the contact matrix.')

# Retain the optical results without substituting their percentages for model accuracy.
light_files={'07_light_response_distribution':'06_light_response_distribution',
             '08_light_metrics_by_taxel':'07_light_metrics_by_taxel',
             '09_light_force_correlation':'08_light_force_correlation'}
old_manifest=json.loads((LIGHT/'figure_manifest.json').read_text())
for source_stem,dest_stem in light_files.items():
    for extension in ['png','svg']:shutil.copy2(LIGHT/'figures'/f'{source_stem}.{extension}',FIG/f'{dest_stem}.{extension}')
    FIGURES.append({'stem':dest_stem,'caption':next(f['caption'] for f in old_manifest if f['stem']==source_stem)})
for filename in ['light_metrics_by_taxel.csv','light_press_by_recording.csv','light_no_contact_by_recording_taxel.csv',
                 'light_fold_reference_floors_and_noise.csv','light_response_distribution_percent.csv','light_force_spearman_by_group_taxel.csv','archive_member_manifest.csv']:
    shutil.copy2(LIGHT/'data'/filename,DATA/filename)
light=pd.read_csv(DATA/'light_metrics_by_taxel.csv')
f=metrics['force'];l=metrics['localization'];c=metrics['contact']
summary=f'''BEST RESULTS — MANUAL CALIBRATION ONLY

Use these three models and the corresponding figures for the main results.

LOCALIZATION — TUNED LOGISTIC REGRESSION
Accuracy: {l['accuracy']:.2%}
Macro F1: {l['macro_f1']:.2%}
Evaluation: 7,154 frames, 54 recordings, nine taxels.

CONTACT DETECTION — TUNED RBF SVC
Accuracy: {c['accuracy']:.2%}
Balanced accuracy: {c['balanced_accuracy']:.2%}
Contact recall: {c['recall']:.2%}
Precision: {c['precision']:.2%}
Specificity: {c['specificity']:.2%}
Contact F1: {c['contact_f1']:.2%}
Macro F1: {c['macro_f1']:.2%}
Raw counts [TN, FP; FN, TP]: {matrices['contact']['raw_counts'].tolist()}
Evaluation: 8,506 frames, 65 recordings.

FORCE ESTIMATION — TUNED ENSEMBLE
MAE: {f['mae_N']:.4f} N
RMSE: {f['rmse_N']:.4f} N
R-squared: {f['r2']:.4f}
Bias: {f['bias_N']:+.4f} N
Evaluation: 7,154 frames, 54 recordings.

METHOD
These are the highest-accuracy evaluated classifiers and the lowest-MAE force estimator on the manual calibration data. Every reported metric gives each recording equal total weight. Predictions come from six outer TEST-group-held-out folds. All recordings are retained in their assigned folds; positive eligibility is the original aligned force interval 0.05-3 N. Contact negatives are the 11 dedicated no-contact recordings. Automatic and replay-only recordings are excluded.

Model-family ranking uses the observed held-out results and is retrospective. The figures summarize fold models; they are not an independent prospective test of a final full-data fit. No new model fitting or score-changing filtering was performed for this consolidation. A single winning model supplies all metrics for each task. Force is regression, so its main result is error in N rather than a classification accuracy percentage.

FIGURES
01: best localization, 9 x 9, row-normalized percentages.
02: best localization, 9 x 9, separately labeled raw counts.
03: best contact detection, 2 x 2, row-normalized percentages.
04: best contact detection, 2 x 2, separately labeled raw counts.
05: spatial taxel performance heatmaps for the two winning classifiers.
06-08: optical response distribution, light metrics, and force-light correlation.

Normalized classification matrices give each frame weight 1/n for its recording, sum weighted outcomes, then normalize each actual-class row to 100%. Raw-count matrices are integer frame totals. Thus a weighted percentage is not obtained simply by dividing the unweighted counts. Rows are actual labels and columns predicted labels. Diagonal normalized values are recall. Accuracy and balanced accuracy are separately labeled.

LIGHT METRICS
No-contact temporal noise: {light.no_contact_rms_within_recording_sd_delta_v.min():.4f}-{light.no_contact_rms_within_recording_sd_delta_v.max():.4f} camera V levels.
Mean target excess response: {light.mean_target_excess_delta_v.min():.3f}-{light.mean_target_excess_delta_v.max():.3f} camera V levels.
Response-to-noise proxy: {light.mean_response_to_noise_ratio.min():.2f}-{light.mean_response_to_noise_ratio.max():.2f}.
Mean active area: {light.mean_active_area_percent.min():.3f}-{light.mean_active_area_percent.max():.3f}% of ROI pixels.

Optical diagnostics use original acquisition frame_features.csv values matched exactly to the same held-out frame identities; these are not claimed to be numerically identical to video-recomputed model features. D is mean positive pixel change from the saved baseline. The reference floor is the median of no-contact recording medians outside the held-out group; excess E=max(D-floor,0). Noise is the RMS of within-recording sample SDs of D in controls. The response/noise proxy uses only out-of-group control noise. Active pixels have delta V >=10. Spatial response profiles normalize each recording's nine mean E values to 100%, then average the six profiles for each pressed taxel; all eligible frames remain included. Force-light correlations are per-recording Spearman correlations using the original aligned force, with no additional lag search. These quantities use camera units, not lux or calibrated physical contact area; manual force histories differ between recordings.

FILES FOR THESIS WRITING
BEST_METRICS.csv and BEST_METRICS.json contain the exact consolidated results.
BEST_MODEL_CONFIGURATIONS.json contains the six winning-family fold configurations and segmentation geometry.
Figure_Captions.txt contains captions for the included PNG and SVG figures.
data/ contains matrices, held-out predictions, taxel metrics and optical diagnostics.
reference/all_competing_models_ranked.csv retains every evaluated model comparison.

All existing reports and competing versions remain in their original locations unchanged.
'''
(OUT/'BEST_RESULTS_SUMMARY.txt').write_text(summary,encoding='utf-8')
(OUT/'Figure_Captions.txt').write_text('\n\n'.join(x['stem']+'\n'+x['caption'] for x in FIGURES),encoding='utf-8')
write_json(OUT/'figure_manifest.json',FIGURES)
check('Every existing report and competing version preserved',all((ROOT/p).is_file() and sha(ROOT/p)==h for p,h in prior.items()))
write_json(OUT/'validation.json',{'checks':CHECKS,'source_prediction_sha256':sha(source),
    'existing_report_files_preserved':len(prior),'visual_review':'pending','model_fit_or_deployment_changed':False})
print(json.dumps(safe({'best_results':metrics,'checks':len(CHECKS),'preserved_files':len(prior),'figures':len(FIGURES)}),indent=2))
