"""Thesis figures from saved manual-only outer-fold predictions, without refitting."""
from pathlib import Path
import json, hashlib, zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle
from sklearn.metrics import confusion_matrix, accuracy_score, balanced_accuracy_score, f1_score

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
RUN=ROOT/'calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909'
PRED=RUN/'outer_predictions.parquet'
DATA=OUT/'data';DATA.mkdir(exist_ok=True)
FIG=OUT/'figures';FIG.mkdir(exist_ok=True)
pred=pd.read_parquet(PRED)
comparison=pd.read_csv(RUN/'model_comparison.csv')
layout=json.loads((ROOT/'calibration_gui/assets/live_sensor/roi_layout.json').read_text())
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':14,'axes.labelsize':12,'svg.fonttype':'none','figure.facecolor':'white','axes.spines.top':False,'axes.spines.right':False})
CHECKS=[];manifest=[];summaries={}
def check(name,condition):
    assert condition,name
    CHECKS.append(name)
def select(task,model='Tuned selected'):
    d=pred[(pred.task==task)&(pred.model==model)].copy()
    check(task+model+' unique frame IDs',not d.frame_uid.duplicated().any())
    check(task+model+' held-out groups',d.group.eq(d.outer_fold).all())
    check(task+model+' six groups',set(d.group)==set(range(1,7)))
    check(task+model+' whole sessions',d.groupby('session_id').outer_fold.nunique().max()==1)
    check(task+model+' complete labels',d[['truth','prediction']].notna().all().all())
    d['truth']=d.truth.astype(int);d['prediction']=d.prediction.astype(int)
    d['recording_weight']=1/d.groupby('session_id').session_id.transform('size')
    return d
def matrices(d,labels,key):
    counts=confusion_matrix(d.truth,d.prediction,labels=labels)
    weighted=confusion_matrix(d.truth,d.prediction,labels=labels,sample_weight=d.recording_weight)
    percent=100*weighted/weighted.sum(axis=1,keepdims=True)
    manual=np.zeros_like(weighted)
    for _,s in d.groupby('session_id'):
        for t,p in zip(s.truth,s.prediction):manual[labels.index(t),labels.index(p)]+=1/len(s)
    check(key+' independently calculated matrix',np.allclose(weighted,manual,atol=1e-12))
    check(key+' count total',counts.sum()==len(d))
    check(key+' percentage row totals',np.allclose(percent.sum(axis=1),100))
    check(key+' equal-recording weight total',np.isclose(weighted.sum(),d.session_id.nunique()))
    for name,m in [('raw_counts',counts),('recording_weighted_counts',weighted),('recording_weighted_row_percent',percent)]:
        df=pd.DataFrame(m,index=labels,columns=labels);df.index.name='actual_class';df.columns.name='predicted_class';df.to_csv(DATA/f'{key}_{name}.csv')
    expected=comparison[(comparison.task==d.task.iloc[0])&(comparison.model==d.model.iloc[0])].iloc[0]
    metrics={'accuracy':accuracy_score(d.truth,d.prediction,sample_weight=d.recording_weight),'balanced_accuracy':balanced_accuracy_score(d.truth,d.prediction,sample_weight=d.recording_weight),'macro_f1':f1_score(d.truth,d.prediction,average='macro',sample_weight=d.recording_weight)}
    for metric,value in metrics.items():check(key+' '+metric+' matches original report',abs(value-expected[metric])<1e-12)
    result={'task':d.task.iloc[0],'model':d.model.iloc[0],'frames':len(d),'recordings':d.session_id.nunique(),'metrics_recording_weighted':metrics,'raw_frame_accuracy':float(np.trace(counts)/counts.sum()),'raw_confusion_matrix':counts.tolist(),'weighted_row_percent':percent.tolist()}
    summaries[key]=result
    return counts,weighted,percent
def save(fig,stem,caption):
    fig.savefig(FIG/(stem+'.png'),dpi=300,facecolor='white')
    fig.savefig(FIG/(stem+'.svg'),facecolor='white')
    plt.close(fig)
    manifest.append({'stem':stem,'caption':caption,'png':f'figures/{stem}.png','svg':f'figures/{stem}.svg'})
def matrix_ax(ax,m,labels,percent=True,title=None,colorbar=True):
    vmax=100 if percent else float(m.max())
    im=ax.imshow(m,cmap='Blues',vmin=0,vmax=vmax,interpolation='nearest')
    ax.set_xticks(range(len(labels)),labels);ax.set_yticks(range(len(labels)),labels)
    ax.set_xlabel('Predicted class',labelpad=10);ax.set_ylabel('Actual class',labelpad=10)
    ax.set_xticks(np.arange(-.5,len(labels),1),minor=True);ax.set_yticks(np.arange(-.5,len(labels),1),minor=True)
    ax.grid(which='minor',color='white',linewidth=1.5);ax.tick_params(which='minor',bottom=False,left=False)
    for i in range(len(labels)):
        for j in range(len(labels)):
            label=f'{m[i,j]:.1f}' if percent else f'{int(m[i,j]):,}'
            ax.text(j,i,label,ha='center',va='center',fontsize=10 if len(labels)>2 else 22,color='white' if m[i,j]>vmax*.57 else '#132A3A')
    if title:ax.set_title(title,pad=14)
    if colorbar:
        cb=ax.figure.colorbar(im,ax=ax,fraction=.042,pad=.035);cb.set_label('Actual-class outcomes (%)' if percent else 'Frames')
    return im
def loc_figure(d,counts,percent,stem,normalized=True,supp=False):
    fig,ax=plt.subplots(figsize=(10,9.2));fig.subplots_adjust(left=.12,right=.91,bottom=.16,top=.83)
    matrix_ax(ax,percent if normalized else counts,[str(i) for i in range(1,10)],percent=normalized)
    fig.suptitle('Localization confusion matrix'+(' — raw counts' if not normalized else ''),x=.12,y=.97,ha='left',fontsize=19,fontweight='bold')
    scope='Tuned ensemble family procedure (supplement)' if supp else 'Tuned nested selection procedure'
    fig.text(.12,.922,f'{scope} | Six held-out TEST groups',fontsize=11)
    fig.text(.12,.89,'7,154 eligible press frames | 54 recordings | Nine ROI classes',fontsize=11)
    note=('Rows sum to 100%; each recording has equal total weight. Cells are percentages.' if normalized else 'Each cell is an integer frame count. These counts do not apply recording weights.')
    fig.text(.12,.085,note,fontsize=10)
    fig.text(.12,.058,'Manual data only; 0.05–3 N. Retrospective evaluation; no training-set predictions.',fontsize=10)
    if supp:fig.text(.12,.031,'Family comparison selected retrospectively; not an independent test of the final full-data refit.',fontsize=9)
    caption=f"Confusion matrix of {scope.lower()} for nine-ROI localization. Rows are true ROI and columns predicted ROI. {note} Evaluation comprises 7,154 positive frames from 54 manual recordings under six outer TEST-group folds. The 0.05–3 N interval remains exploratory."
    save(fig,stem,caption)
def contact_figure(d,counts,percent,stem,supp=False):
    fig,axes=plt.subplots(1,2,figsize=(12.6,7.4));fig.subplots_adjust(left=.1,right=.96,bottom=.30,top=.76,wspace=.38)
    matrix_ax(axes[0],percent,['No contact','Contact'],title='Equal-recording outcomes (%)',colorbar=False)
    matrix_ax(axes[1],counts,['No contact','Contact'],percent=False,title='Raw frame counts',colorbar=False)
    fig.suptitle('Contact-detection confusion matrices',x=.08,y=.97,ha='left',fontsize=20,fontweight='bold')
    scope='Tuned RBF SVC family procedure (supplement)' if supp else 'Tuned nested selection procedure'
    fig.text(.08,.90,f'{scope} | Six held-out TEST groups',fontsize=11)
    fig.text(.08,.855,'8,506 frames | 65 recordings | 1,352 no-contact and 7,154 eligible contact frames',fontsize=11)
    fig.text(.08,.16,'Left: rows sum to 100% after equal-recording weighting. Right: unweighted integer counts.',fontsize=10)
    fig.text(.08,.115,'TN = upper left; FP = upper right; FN = lower left; TP = lower right.',fontsize=10)
    fig.text(.08,.075,'Zero observed false positives covers 11 no-contact recordings; it does not establish zero future risk.',fontsize=10)
    if supp:fig.text(.08,.035,'Retrospective family comparison; not an independent test of the final full-data SVC refit.',fontsize=9)
    save(fig,stem,f"Binary confusion matrices for the {scope.lower()}. Rows denote actual status and columns predicted status. The left panel uses equal-recording row percentages; the right panel reports raw frame counts. Contact positives are aligned press frames in 0.05–3 N; negatives are dedicated no-contact frames. Zero observed false positives is limited to 11 archived no-contact recordings.")

loc=select('localization');con=select('contact')
check('eligible manual roles only',set(con.scientific_role)=={'model_primary','no_contact'} and set(loc.scientific_role)=={'model_primary'})
check('positive frame identities agree',set(loc.frame_uid)==set(con[con.truth==1].frame_uid))
lc,lw,lp=matrices(loc,list(range(1,10)),'localization_selected')
cc,cw,cp=matrices(con,[0,1],'contact_selected')
loc_figure(loc,lc,lp,'01_localization_confusion_weighted')
loc_figure(loc,lc,lp,'02_localization_confusion_counts',normalized=False)
contact_figure(con,cc,cp,'03_contact_confusion_matrices')

# Per-ROI maps are performance summaries, not predicted contact intensity fields.
roi=[]
for i in range(1,10):
    a=loc[loc.truth==i];b=con[(con.truth==1)&(con.target_roi==i)]
    lr=a.assign(correct=a.truth.eq(a.prediction)).groupby('session_id').correct.mean().mean()
    cr=b.groupby('session_id').prediction.mean().mean()
    check(f'ROI {i} recall equals confusion diagonal',np.isclose(lr*100,lp[i-1,i-1]))
    roi.append({'roi':i,'press_frames':len(a),'press_recordings':a.session_id.nunique(),'localization_recall_percent':100*lr,'contact_recall_percent':100*cr})
roi=pd.DataFrame(roi);roi.to_csv(DATA/'roi_performance.csv',index=False)
fig,axes=plt.subplots(1,2,figsize=(12,9));fig.subplots_adjust(left=.07,right=.87,bottom=.16,top=.83,wspace=.22)
cmap=plt.get_cmap('Blues');norm=Normalize(0,100)
for ax,metric,title in zip(axes,['localization_recall_percent','contact_recall_percent'],['Localization recall','Contact-detection recall']):
    ax.set_xlim(65,405);ax.set_ylim(490,125);ax.set_aspect('equal');ax.set_xlabel('Image x coordinate (pixels)');ax.set_ylabel('Image y coordinate (pixels)');ax.set_title(title,pad=15)
    for rect in layout['rois']:
        i=rect['roi_id'];value=roi.set_index('roi').loc[i,metric]
        ax.add_patch(Rectangle((rect['x'],rect['y']),rect['width'],rect['height'],facecolor=cmap(norm(value)),edgecolor='#455B6D',linewidth=.9))
        ax.text(rect['center_x'],rect['center_y'],f'ROI {i}\n{value:.1f}%',ha='center',va='center',fontsize=11,fontweight='bold',color='white' if value>57 else '#132A3A')
cbax=fig.add_axes([.91,.25,.018,.45]);cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cbax);cb.set_label('Recall (%)')
fig.suptitle('Performance across the sensing regions',x=.07,y=.97,ha='left',fontsize=20,fontweight='bold')
fig.text(.07,.925,'Tuned nested selector | Actual ROI rectangles in the oriented camera image',fontsize=11)
fig.text(.07,.89,'Each ROI: six held-out press recordings | Percentages give recordings equal weight',fontsize=11)
fig.text(.07,.11,'Left: correct ROI given true ROI. Right: contact detected given a positive press at that ROI.',fontsize=10)
fig.text(.07,.077,'Zoomed pixel layout; image y increases downward. Colors show evaluation recall, not optical intensity.',fontsize=10)
fig.text(.07,.044,'No-contact specificity is assessed separately; this map does not imply continuous spatial resolution.',fontsize=10)
save(fig,'04_roi_performance_heatmaps','Localization and positive-contact recall mapped to the nine fixed ROI rectangles in the 480 by 640 oriented image, shown as a zoomed view. Each value averages six recording-specific recalls. The contact panel excludes no-contact recordings. Colors represent historical classification performance, not instantaneous model output, optical intensity, force or a continuous spatial field.')

group_rows=[]
for g in range(1,7):
    for i in range(1,10):
        a=loc[(loc.group==g)&(loc.truth==i)]
        group_rows.append({'test_group':g,'roi':i,'frames':len(a),'accuracy_percent':100*a.truth.eq(a.prediction).mean()})
gr=pd.DataFrame(group_rows);gr.to_csv(DATA/'localization_by_group_roi.csv',index=False)
mat=gr.pivot(index='test_group',columns='roi',values='accuracy_percent').to_numpy()
fig,ax=plt.subplots(figsize=(11.5,7.4));fig.subplots_adjust(left=.12,right=.91,bottom=.20,top=.78)
im=ax.imshow(mat,cmap='Blues',vmin=0,vmax=100,aspect='auto')
ax.set_xticks(range(9),[f'ROI {i}' for i in range(1,10)]);ax.set_yticks(range(6),[f'TEST {i}' for i in range(1,7)])
ax.set_xlabel('True ROI',labelpad=12);ax.set_ylabel('Held-out recording group',labelpad=12)
for y in range(6):
    for x in range(9):ax.text(x,y,f'{mat[y,x]:.1f}',ha='center',va='center',color='white' if mat[y,x]>57 else '#132A3A',fontsize=11)
ax.set_xticks(np.arange(-.5,9,1),minor=True);ax.set_yticks(np.arange(-.5,6,1),minor=True);ax.grid(which='minor',color='white',linewidth=1.3);ax.tick_params(which='minor',left=False,bottom=False)
fig.colorbar(im,ax=ax,fraction=.035,pad=.025,label='Correct localization (%)')
fig.suptitle('Localization by held-out group and ROI',x=.12,y=.96,ha='left',fontsize=20,fontweight='bold')
fig.text(.12,.905,'Tuned nested selector | Each cell describes one complete press recording',fontsize=11)
fig.text(.12,.86,'54 recordings | 7,154 eligible frames | Fixed 0–100% scale',fontsize=11)
fig.text(.12,.10,'Values are correct-ROI percentages within each recording; cell frame counts are supplied in CSV.',fontsize=10)
fig.text(.12,.065,'Retrospective manual-only evaluation. This diagnostic preserves TEST1 and every recorded ROI.',fontsize=10)
save(fig,'05_localization_group_roi_heatmap','Localization accuracy within each of 54 held-out press recordings, arranged by TEST group and true ROI. Each cell represents one recording and all cells use a fixed 0–100% scale. The figure shows recording-level variation that is obscured by pooled accuracy; per-cell frame denominators are provided in localization_by_group_roi.csv.')

# The final full-data fit uses ensemble localization and an SVC contact model.
# These supplementary matrices evaluate those family procedures in outer folds,
# not the final estimators on their own fitting data.
sl=select('localization','Tuned ensemble');a,b,c=matrices(sl,list(range(1,10)),'localization_ensemble_family')
loc_figure(sl,a,c,'06_supplement_localization_ensemble',supp=True)
sc=select('contact','Tuned RBF SVC');a,b,c=matrices(sc,[0,1],'contact_svc_family')
contact_figure(sc,a,c,'07_supplement_contact_svc',supp=True)

off=lp.copy();np.fill_diagonal(off,0)
mistakes=[{'actual_roi':int(y+1),'predicted_roi':int(x+1),'weighted_percent':float(off[y,x]),'raw_frames':int(lc[y,x])} for y,x in np.dstack(np.unravel_index(np.argsort(off.ravel())[::-1][:5],off.shape))[0]]
payload={'created_on':'2026-10-15','experiment':'tuning_20260909','primary_model':'Tuned selected','source_prediction_sha256':hashlib.sha256(PRED.read_bytes()).hexdigest(),'definitions':{'primary':'Nested selection evaluated on six complete outer TEST groups','weighted_matrix':'Each frame gets weight 1/(eligible frames in its recording); normalize each actual-class row to 100%.','raw_matrix':'Unweighted integer frame counts','spatial_map':'Performance per true ROI, not a pixelwise prediction or force map','refit':'No final full-data estimator is evaluated on its own training rows here.'},'summaries':summaries,'top_localization_confusions':mistakes,'checks':CHECKS,'visual_review':'pending'}
(OUT/'metrics_and_validation.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
(OUT/'figure_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
captions='THESIS FIGURE CAPTIONS\n\n'+'\n\n'.join(f"{m['stem']}\n{m['caption']}" for m in manifest)
(OUT/'Figure_Captions.txt').write_text(captions,encoding='utf-8')
readme=f'''MANUAL CALIBRATION CONFUSION MATRICES AND HEATMAPS
Created 15 October 2026 from the saved 9 September 2026 tuning experiment.

Use figures 01, 03 and 04 as the primary thesis figures. Figure 02 supplies raw localization counts; figure 05 exposes group variation. Each figure is supplied as a 300 dpi PNG and editable vector SVG. SVG files preserve text as text.

Primary procedure: Tuned selected. These are held-out outer-fold predictions from a nested selection procedure, not predictions of the final full-data fit on its own training data. Models and thresholds may differ across outer folds. The saved final fitted model has no separate untouched prospective test set.

The manual archive alone supplied these experiments. Localization: 7,154 eligible press frames from 54 recordings and nine ROIs. Contact: those positives plus 1,352 frames from 11 dedicated no-contact recordings. Press eligibility is aligned force 0.05–3 N, an exploratory interval. Replay-only recordings are excluded.

Matrix rows are actual labels; columns are predicted labels. Normalized figures give each recording equal total weight before row normalization. Raw-count figures count every frame equally. Consequently, percentages calculated from raw counts can differ from the published recording-balanced metrics; do not mix them.

Primary recording-balanced localization accuracy: {summaries['localization_selected']['metrics_recording_weighted']['accuracy']:.8%}
Primary recording-balanced localization macro F1: {summaries['localization_selected']['metrics_recording_weighted']['macro_f1']:.8%}
Primary contact balanced accuracy: {summaries['contact_selected']['metrics_recording_weighted']['balanced_accuracy']:.8%}
Primary contact raw counts [TN, FP; FN, TP]: {cc.tolist()}

The spatial map uses the actual nine rectangular ROIs in pixel coordinates, with image y increasing downward. Colors are classification recall, not sensor intensity, force or a continuous localization estimate. Its contact panel includes positive press frames only. No-contact specificity is shown in the binary confusion matrix, not inferred for individual ROI rectangles.

Figures 06 and 07 are supplementary retrospective family comparisons: Tuned ensemble localization and Tuned RBF SVC contact. These correspond to the families selected for the final saved models but use separately trained fold models. They should not replace the primary nested-selector metrics without explaining the different comparison.

No training or data filtering was changed for this export. The zero false-positive count is limited to the 11 archived no-contact recordings. The recordings were used in prior development; these are retrospective results, not prospective validation. Force regression has continuous outputs and is not represented with a classification confusion matrix.

Source: calibration_gui/analysis_outputs/live_sensor_manual_only/model_runs/tuning_20260909/outer_predictions.parquet
Model labels and metrics were cross-checked against model_comparison.csv. Matrix cells were independently reconstructed by recording and every row-normalized matrix sums to 100%. Counts and plotting inputs are supplied in data/. Figure_Captions.txt contains thesis-ready captions. Run build_figures.py with calibration_gui/.venv/Scripts/python.exe to reproduce.
'''
(OUT/'README.txt').write_text(readme,encoding='utf-8')
print(json.dumps({'figures':len(manifest),'checks':len(CHECKS),'localization_counts':lc.tolist(),'contact_counts':cc.tolist(),'contact_weighted_row_percent':cp.tolist(),'top_confusions':mistakes},indent=2))
